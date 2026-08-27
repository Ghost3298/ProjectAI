# CLAUDE.md

## Project

**VOICE** — an Arabic-first, fully local speaker biometrics and speech
intelligence system. Upload or record audio → transcript → speaker-labeled
timeline → enrolled-speaker recognition → summary + entities. Nothing leaves
the machine at inference time (privacy requirement from the proposal).

Reference doc: `Project_Proposal_Hiba_Eddy.docx` (Sections G/H/J/M define
scope, success metrics, work plan, and the Claude-usage declaration
requirement — read it before making scope decisions).

Team: Hiba (frontend flow, eval data, annotations, summary/entity
evaluation) and Eddy (Docker/GPU, FastAPI/Celery pipeline, transcription,
diarization, speaker recognition). Both: integration testing, tuning, docs,
demo.

## Tech stack

- **`ui/`** — Angular (standalone components, signals, zoneless change
  detection, Angular Material). Talks to the API via `HttpClient`.
- **`api/`** — FastAPI + Celery. One Docker image, two services (`api` runs
  uvicorn, `worker` runs `celery worker --pool=solo`).
- **Postgres** — job/turn/speaker records (SQLAlchemy ORM).
- **MinIO** — S3-compatible object storage for raw audio.
- **Valkey** — Celery broker + result backend (Redis-compatible, password
  auth via `--requirepass`).
- **Faster-Whisper** (`"small"`, `device="cuda"`, `compute_type="float16"`) —
  transcription, auto-detected language (not forced to Arabic — forcing it
  garbles non-Arabic speech into phonetic Arabic script instead of failing
  cleanly).
- **NVIDIA NeMo** (`SortformerEncLabelModel`, `nvidia/diar_sortformer_4spk-v1`)
  — diarization. **Session length ~90s** — longer audio MUST be chunked
  (~60s windows) with timestamps offset back to the full recording's
  timeline, or it crashes with a vague CUDA error.
- **NeMo Titanet** (`titanet_large`) — speaker embeddings for enrollment/
  recognition, cosine similarity against enrolled `Speaker` rows.
- **vLLM + Qwen2.5-3B-Instruct** — separate container, OpenAI-compatible
  API on port 8001, used for summarization/entity extraction/translation.
- **FFmpeg** — normalizes all incoming audio (any format) to 16kHz mono WAV
  before either model touches it. **Required**, not optional — NeMo's audio
  backend rejects WebM/Opus outright (`Format not recognised`); Whisper
  tolerates it but shouldn't rely on that.

## Architecture

```
ui (Angular, :4200) → api (FastAPI, :8000) → Postgres (job/turn/speaker rows)
                                            → MinIO (raw audio)
                                            → Valkey (Celery broker)
worker (Celery, --pool=solo) ← polls Valkey → runs pipeline, updates Postgres
llm (vLLM, :8001) ← called by worker for summarization/translation
```

Upload flow: `POST /jobs` → MinIO upload → Postgres `Job` row
(`status="queued"`) → `db.commit()` → **then** `.delay()` the Celery task
(never enqueue before commit — race condition, worker can query a
nonexistent row). UI polls `GET /jobs/{id}` every 2s per job via a
`Map<jobId, intervalHandle>` (not one shared handle — breaks with multiple
concurrent jobs).

Pipeline (`process_job` in `celery_app.py`): download from MinIO → FFmpeg
normalize → Whisper transcribe → NeMo diarize (chunked) → Titanet embed +
match each turn against enrolled speakers → Qwen2.5 summarize/extract →
write everything to Postgres → `status="done"`.

## Critical GPU/environment gotchas (do not relitigate these)

These cost real debugging time across two machines (a laptop RTX 4060 on
Parrot OS, a PC RTX 5060 on Windows/WSL2). Read before touching anything
GPU-related.

- **`api/Dockerfile` MUST use `FROM python:3.11-slim-bookworm`**, not plain
  `python:3.11-slim`. Unpinned `slim` floats to newer Debian releases with
  glibc 2.41+, which refuses to load CTranslate2's compiled binary
  (`cannot enable executable stack as shared object requires`). Any
  unpinned base image tag can silently change under you — same class of
  risk as `postgres:latest`.
- **`requirements.txt` pins `ctranslate2==4.4.0` and
  `nvidia-cudnn-cu12==8.9.7.29` together.** cuDNN 9 restructured its
  library layout; CTranslate2 releases before ~4.5 expect cuDNN 8's layout
  and fail with a vague `CUDA failed with error unknown error` if given
  cuDNN 9. NeMo's own PyTorch dependency does NOT appear to force a cuDNN
  upgrade when installed via `nemo_toolkit[asr]` — verified empirically,
  but re-check `pip show nvidia-cudnn-cu12` after any dependency change.
- **`worker`'s `environment:` needs `NVIDIA_VISIBLE_DEVICES: all` and
  `NVIDIA_DRIVER_CAPABILITIES: compute,utility` set explicitly.** The
  `deploy.resources.reservations.devices.capabilities: [gpu]` block is
  NOT a real capability string and can silently fall back to NVML-only
  access (`nvidia-smi` works, CUDA itself doesn't). Don't rely on
  `deploy:` translation alone.
- **On Linux (Parrot OS etc.):** install NVIDIA Container Toolkit host-side
  (`nvidia-ctk runtime configure --runtime=docker` + restart Docker) —
  once per machine, not per project.
- **On Windows (Docker Desktop + WSL2):** none of the above toolkit setup
  is needed or correct — GPU passthrough works out of the box via
  `--gpus all`. Don't run Linux toolkit install steps there.
- **`api/Dockerfile`'s pip install MUST use a cache mount**, or every
  `requirements.txt` change triggers a full redownload of everything
  (multi-GB, hours):
  ```dockerfile
  RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
  ```
- **`worker` has a named volume for the Hugging Face cache**
  (`hf_cache:/root/.cache/huggingface`) so model weights persist across
  rebuilds. Without it, every rebuild re-downloads Whisper/NeMo/Qwen
  weights from scratch.
- **`docker compose build` does NOT restart the running container** — it
  only builds the image. Use `docker compose up -d --build` (build +
  recreate) or `docker compose up -d --force-recreate` after a plain
  `build`, or you'll be testing a stale container indefinitely.
- **Model loading is lazy and cached at module level per worker process**
  (`get_whisper_model()`, `get_diarization_model()`, `get_titanet_model()`
  — each a `None` global + guard). Never load models at import time in
  `celery_app.py` — `api` imports from that file too (for `.delay()`
  calls), and `api` never gets GPU access, so an eager model load there
  crashes the whole API container on startup.
- **Celery MUST run `--pool=solo`.** Default prefork forking is not
  CUDA-safe; forked children can inherit a broken CUDA context. This
  matters more than concurrency — you won't get meaningful GPU parallelism
  from prefork anyway on a single 8GB card.
- **Measured VRAM (RTX 5060, 8GB card):** baseline ~750MB, +Whisper small
  ~730MB, +Sortformer ~915MB. Comfortable headroom. Re-measure with
  `nvidia-smi --query-gpu=memory.used --format=csv` after adding Titanet
  and vLLM — don't assume, measure.
- **First model load per worker boot takes several minutes** (CUDA
  init/kernel compilation), separate from the HF download. Don't mistake
  this for a hang.

## Conventions

- Every service's `environment:` block must be updated explicitly when its
  code starts needing a new credential — `api` and `worker` share one
  Docker image but do NOT automatically share environment variables.
- `.env` holds all credentials; `docker-compose.yml` references them via
  `${VAR}`. Healthchecks needing the same value inside the container use
  `$$VAR` (shell-side resolution) not `${VAR}` (Compose-side).
- Changing `.env` alone does nothing to a running container — needs
  `--force-recreate` or `up -d --build`.
- UUID primary keys everywhere (`Uuid(as_uuid=True)`, `default=uuid.uuid4`).
- New tables only get created (`Base.metadata.create_all`) once imported
  somewhere `main.py` actually loads — `Translation` is defined in
  `models.py` but deliberately not yet imported/created, since nothing
  writes to it until the Week 3 translation endpoint exists.
- FastAPI service (`api`) never touches CUDA directly — it only enqueues
  Celery tasks. All model code lives in `celery_app.py`, executed by
  `worker`.

## Current status (Week 2, in progress)

**Done and verified on both machines:**
- Full Week 1 pipeline: upload (file or mic recording) → MinIO → Postgres
  → Celery → FFmpeg normalize → Whisper transcribe (auto-detected
  language) → status polling → transcript shown in Angular UI.
- `Job`, `Translation`, `Turn` SQLAlchemy models exist. `Turn` has a real
  FK to `jobs.id`; `speaker_id` column exists (`Uuid`, nullable) but has
  no FK constraint yet since `speakers` table doesn't exist.
- NeMo Sortformer diarization integrated and verified working on short
  clips (produces real `Turn` rows with correct start/end/speaker_label).
- Confirmed via isolated testing: NeMo + Faster-Whisper coexist fine in
  the same container/process, VRAM headroom is comfortable.
- Confirmed bug and root cause: long audio (~8min) crashes Sortformer
  (`CUDA driver error: device not ready`) — session length limit, needs
  chunking (not yet implemented in the real pipeline).
- Confirmed and fixed a real Whisper truncation bug (was cutting off
  transcripts early — needed inspecting segment count/end-timestamp vs.
  actual duration to diagnose; specific VAD-related fix applied and
  verified working).

**Not yet done (see `VOICE_Completion_Guide.md` for full ready-to-use code
for all of this):**
1. Chunked diarization wired into the real `process_job` (code drafted,
   not yet applied/tested against long real audio).
2. `Speaker` model + enrollment endpoint (`POST /speakers`,
   `GET /speakers`).
3. Titanet embedding extraction + cosine-similarity matching wired into
   `process_job` (per-turn, with a minimum-duration guard before
   attempting a match).
4. Angular enrollment UI + speaker-labeled timeline in the results view
   (currently `GET /jobs/{id}` returns only flat transcript text, no
   turns).
5. `llm` service (vLLM + Qwen2.5-3B-Instruct) — not yet brought up.
6. Summarization/entity extraction task, translation endpoint (both
   depend on #5).
7. `"failed"` job status + try/except wrapping in `process_job` — right
   now a crash leaves a job stuck at `"processing"` forever with no
   distinction from "still working."
8. The ~20-clip evaluation set (manual work, not code) — required before
   any of the proposal's numeric targets (WER ≤25%, ≥80% speaker
   attribution, etc.) can actually be measured.
9. `GET /jobs` list endpoint + wiring the History panel (still shows the
   Angular empty state).

## Next explicit steps, in order

1. Apply chunked diarization to `process_job`, test against a real long
   recording (8+ min), confirm turns land correctly with offset timestamps
   and no crash.
2. Add `Speaker` model, enrollment endpoint, Titanet extraction/matching.
   Test: enroll 1-2 speakers via curl or the API docs UI, upload a
   multi-speaker clip, confirm `turns.speaker_id` gets populated correctly
   for matched turns and stays `NULL` for unmatched/below-threshold ones.
3. Wire enrollment + speaker timeline into the Angular UI.
4. Bring up the `llm` service standalone, confirm `curl
   http://localhost:8001/v1/models` responds before writing any code
   against it.
5. Add summarization/entity extraction to `process_job`, add translation
   endpoint. Test both against real transcripts.
6. Add `"failed"` status handling (small, do this early — prevents
   confusing silent hangs while testing everything else above).
7. Build the real evaluation set with Hiba (~20 clips: single/multi
   speaker, some enrolled, one noisy, one invalid file, manually
   annotated).
8. Run WER/speaker-attribution scoring against the eval set; tune
   `SIMILARITY_THRESHOLD` (currently a guessed `0.6`) and model sizes
   against real numbers, not assumptions.
9. `GET /jobs` list endpoint + History panel wiring.
10. Demo prep per proposal Section G: rehearsed single-speaker and
    multi-speaker (with enrolled ID) examples, results table for the
    metrics above, explicit awareness of what's out of scope so it's
    never implied as working.

Full ready-to-use code for steps 1-6 already exists in
`VOICE_Completion_Guide.md` in this repo — apply it directly rather than
regenerating from scratch, then test/debug against real hardware.