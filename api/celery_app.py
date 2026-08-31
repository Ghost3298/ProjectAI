import subprocess
from celery import Celery
import os, time, wave, json
import numpy as np
import requests
from models import Job, Turn, Speaker
from db import get_db_context
from storage import s3_client
from faster_whisper import WhisperModel
import tempfile
from nemo.collections.asr.models import SortformerEncLabelModel, EncDecSpeakerLabelModel
import torch

app = Celery(
    'tasks',
    broker=os.environ.get('CELERY_BROKER_URL'),
    backend=os.environ.get('CELERY_RESULT_BACKEND')
)

whisper_model = None
diarization_model = None
titanet_model = None

# Sortformer's session length is ~90s before it crashes with a vague CUDA
# error, so any audio longer than that must be diarized in windows with
# timestamps offset back onto the full recording's timeline.
DIARIZATION_CHUNK_SECONDS = 60.0
DIARIZATION_MAX_SINGLE_PASS_SECONDS = 90.0

# Whisper detects language ONCE from roughly the first ~30s of audio, then
# transcribes the ENTIRE recording using that single language. A recording
# that starts in English and switches to Arabic (or vice versa) gets the
# Arabic portion force-decoded as English - the model does its best to
# output English-sounding words for audio it's been told is English,
# which is why a language switch shows up looking "translated" instead of
# transcribed. Re-detecting language every chunk catches a mid-recording
# switch at roughly this granularity.
TRANSCRIPTION_CHUNK_SECONDS = 30.0

# Titanet embeddings on clips shorter than this are unreliable, so those
# turns keep their raw (possibly chunk-local) diarization label instead of
# being voice-clustered.
MIN_EMBEDDING_DURATION_SECONDS = 0.5
# How similar two turns' voice embeddings must be to be treated as the same
# speaker within one recording (keeps a speaker's label consistent across
# chunked-diarization boundaries, where NeMo's own labels reset every ~60s).
# Guessed, like ENROLLED_MATCH_THRESHOLD below - not tuned against real eval
# data yet (see backlog item to tune both against real numbers).
CLUSTER_SIMILARITY_THRESHOLD = 0.6
# How similar a speaker cluster's voice must be to an enrolled Speaker's
# embedding to tag turns with that person's identity. Guessed, not tuned
# against real eval data yet.
ENROLLED_MATCH_THRESHOLD = 0.6

LLM_API_BASE = os.environ.get("LLM_API_BASE", "http://llm:8000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-3B-Instruct-AWQ")
# Qwen2.5-3B's context is small and shared with the prompt + output, so the
# transcript is truncated rather than risking a context-length error on long
# recordings. Good enough for a summary; not meant for verbatim recall.
LLM_MAX_TRANSCRIPT_CHARS = 6000

SUMMARY_SYSTEM_PROMPT = (
    "You read a speech transcript and produce a concise summary plus key "
    "entities mentioned in it. Always respond in the SAME language the "
    "transcript is written in - never translate it. Respond with strict "
    "JSON only, no markdown formatting, no code fences, matching exactly "
    "this shape: "
    '{"summary": "2-4 sentence summary", '
    '"entities": [{"type": "person|organization|date|location|other", "value": "..."}]}'
)

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        # "small" struggled with Lebanese/Levantine Arabic specifically (a
        # lower-resource dialect Whisper sees less of in training). "medium"
        # (~1.5GB VRAM vs small's ~730MB) is meaningfully more accurate on
        # dialectal speech - still fits this 8GB card alongside NeMo/Titanet/
        # vLLM. Not switching to large-v3 (~3GB): too tight alongside vLLM's
        # own ~2.8GB reservation.
        whisper_model = WhisperModel("medium", device="cuda", compute_type="float16")
    return whisper_model

def get_diarization_model():
    global diarization_model
    if diarization_model is None:
        diarization_model = SortformerEncLabelModel.from_pretrained('nvidia/diar_sortformer_4spk-v1')
    return diarization_model

def get_titanet_model():
    global titanet_model
    if titanet_model is None:
        titanet_model = EncDecSpeakerLabelModel.from_pretrained('titanet_large')
    return titanet_model

@app.task
def add(x, y):
    time.sleep(5)
    return x + y

def get_wav_duration_seconds(wav_path):
    with wave.open(wav_path, 'rb') as wf:
        return wf.getnframes() / float(wf.getframerate())

def parse_diarization_segments(diarization_result, offset_seconds=0.0, chunk_index=0):
    turns = []
    for segment_str in diarization_result[0]:
        start_str, end_str, speaker_label = segment_str.split()
        turns.append((offset_seconds + float(start_str), offset_seconds + float(end_str), speaker_label, chunk_index))
    return turns

def merge_adjacent_same_speaker_turns(turns, max_gap_seconds=0.5):
    if not turns:
        return []

    merged = [list(turns[0])]
    for start, end, speaker_label in turns[1:]:
        last = merged[-1]
        if speaker_label == last[2] and start - last[1] <= max_gap_seconds:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end, speaker_label])

    return [tuple(t) for t in merged]

def assign_text_to_turns(turns, segments_list):
    # Word-level, not segment-level: a single Whisper segment can span a
    # speaker change when there's no real pause between two people talking
    # (e.g. quick back-and-forth), and assigning the whole segment's text to
    # one turn would silently merge both speakers' lines under one label.
    # Nearest-turn, not strict containment: a word landing in the small gap
    # between two diarization turns (common - VAD/diarization boundaries
    # rarely line up exactly) would otherwise be silently dropped instead of
    # attributed to whichever speaker actually said it.
    words = [word for segment in segments_list for word in (segment.words or [])]
    words_per_turn = [[] for _ in turns]

    for word in words:
        mid = (word.start + word.end) / 2
        best_index, best_distance = None, None
        for index, (start, end, _label) in enumerate(turns):
            distance = 0.0 if start <= mid < end else min(abs(mid - start), abs(mid - end))
            if best_distance is None or distance < best_distance:
                best_index, best_distance = index, distance
        if best_index is not None:
            words_per_turn[best_index].append(word.word.strip())

    return [
        (start, end, speaker_label, " ".join(turn_words).strip() or None)
        for (start, end, speaker_label), turn_words in zip(turns, words_per_turn)
    ]

def cosine_similarity(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def extract_turn_embedding(titanet_model_instance, wav_path, start, end):
    if end - start < MIN_EMBEDDING_DURATION_SECONDS:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav") as clip_file:
        subprocess.run(
            [
                'ffmpeg', '-y', '-i', wav_path,
                '-ss', str(start), '-t', str(end - start),
                '-ar', '16000', '-ac', '1', clip_file.name,
            ],
            check=True,
        )
        embedding = titanet_model_instance.get_embedding(clip_file.name)
    return embedding.squeeze().cpu().numpy()

def build_diarization_group_embeddings(titanet_model_instance, wav_path, turns):
    # Diarization's own speaker_label resets across chunk boundaries (each
    # ~60s chunk is diarized independently) - it can't be trusted as a stable
    # identity for the whole recording. One embedding per (chunk, raw label)
    # group is extracted from that group's single longest window, since a
    # long sample gives a far more reliable voice embedding than any of the
    # (often sub-second) individual turns clustered per-turn would.
    windows_by_group = {}
    for start, end, speaker_label, chunk_index in turns:
        windows_by_group.setdefault((chunk_index, speaker_label), []).append((start, end))

    embeddings = {}
    for group_key, windows in windows_by_group.items():
        longest_start, longest_end = max(windows, key=lambda w: w[1] - w[0])
        embeddings[group_key] = extract_turn_embedding(titanet_model_instance, wav_path, longest_start, longest_end)
    return embeddings

def cluster_diarization_groups(group_embeddings):
    clusters = []  # each: {"label": str, "embeddings": [np.ndarray], "centroid": np.ndarray}
    group_to_label = {}

    for group_key, embedding in group_embeddings.items():
        if embedding is None:
            chunk_index, raw_label = group_key
            group_to_label[group_key] = f"speaker_{chunk_index}_{raw_label}"
            continue

        best_cluster, best_similarity = None, -1.0
        for cluster in clusters:
            similarity = cosine_similarity(embedding, cluster["centroid"])
            if similarity > best_similarity:
                best_cluster, best_similarity = cluster, similarity

        if best_cluster is not None and best_similarity >= CLUSTER_SIMILARITY_THRESHOLD:
            best_cluster["embeddings"].append(embedding)
            best_cluster["centroid"] = np.mean(best_cluster["embeddings"], axis=0)
            label = best_cluster["label"]
        else:
            label = f"speaker_{len(clusters)}"
            clusters.append({"label": label, "embeddings": [embedding], "centroid": embedding})

        group_to_label[group_key] = label

    return group_to_label, clusters

def match_clusters_to_enrolled_speakers(clusters, enrolled_speakers):
    # enrolled_speakers: list of (speaker_id, name, embedding)
    matches = {}
    for cluster in clusters:
        best_id, best_name, best_similarity = None, None, -1.0
        for speaker_id, name, embedding in enrolled_speakers:
            similarity = cosine_similarity(cluster["centroid"], embedding)
            if similarity > best_similarity:
                best_id, best_name, best_similarity = speaker_id, name, similarity
        if best_id is not None and best_similarity >= ENROLLED_MATCH_THRESHOLD:
            matches[cluster["label"]] = (best_id, best_name)
    return matches

def summarize_and_extract_entities(transcript_text):
    if not transcript_text or not transcript_text.strip():
        return None, []

    response = requests.post(
        f"{LLM_API_BASE}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript_text[:LLM_MAX_TRANSCRIPT_CHARS]},
            ],
            "temperature": 0.2,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    parsed = json.loads(content)
    summary = parsed.get("summary")
    entities = parsed.get("entities", [])
    if not isinstance(entities, list):
        entities = []

    return summary, entities

def compute_chunk_bounds(duration, chunk_seconds, min_last_chunk_seconds=10.0):
    # A final leftover shorter than this (e.g. a 2.8s tail) doesn't give
    # Whisper enough audio to detect its language reliably - merging it into
    # the previous chunk instead of transcribing it standalone avoids that.
    bounds = []
    offset = 0.0
    while offset < duration:
        remaining = duration - offset
        if remaining <= chunk_seconds:
            if bounds and remaining < min_last_chunk_seconds:
                prev_start, _ = bounds[-1]
                bounds[-1] = (prev_start, duration)
            else:
                bounds.append((offset, duration))
            break
        bounds.append((offset, offset + chunk_seconds))
        offset += chunk_seconds
    return bounds

def transcribe_audio(model, wav_path):
    duration = get_wav_duration_seconds(wav_path)

    all_segments = []
    languages = []  # (chunk_duration, language) - majority-duration language wins as the job's overall detected_language
    for offset, chunk_end in compute_chunk_bounds(duration, TRANSCRIPTION_CHUNK_SECONDS):
        chunk_len = chunk_end - offset
        with tempfile.NamedTemporaryFile(suffix=".wav") as chunk_file:
            subprocess.run(
                [
                    'ffmpeg', '-y', '-i', wav_path,
                    '-ss', str(offset), '-t', str(chunk_len),
                    '-ar', '16000', '-ac', '1', chunk_file.name,
                ],
                check=True,
            )
            # No language= forced: Whisper only has a single "ar" code
            # covering every Arabic dialect (Gulf, Egyptian, Levantine,
            # Maghrebi, ...), and every other language, so auto-detect is
            # both correct and dialect-agnostic. Forcing "ar" garbles
            # non-Arabic speech into phonetic Arabic script instead of
            # failing cleanly.
            segments, info = model.transcribe(chunk_file.name, vad_filter=True, word_timestamps=True)
            for segment in segments:
                segment.start += offset
                segment.end += offset
                if segment.words:
                    for word in segment.words:
                        word.start += offset
                        word.end += offset
                all_segments.append(segment)
            languages.append((chunk_len, info.language))

    detected_language = max(languages, key=lambda pair: pair[0])[1] if languages else None
    return all_segments, detected_language

def diarize_audio(diarization_model_instance, wav_path):
    duration = get_wav_duration_seconds(wav_path)

    if duration <= DIARIZATION_MAX_SINGLE_PASS_SECONDS:
        result = diarization_model_instance.diarize(audio=[wav_path], batch_size=1)
        return parse_diarization_segments(result)

    turns = []
    offset = 0.0
    chunk_index = 0
    while offset < duration:
        chunk_len = min(DIARIZATION_CHUNK_SECONDS, duration - offset)
        with tempfile.NamedTemporaryFile(suffix=".wav") as chunk_file:
            subprocess.run(
                [
                    'ffmpeg', '-y', '-i', wav_path,
                    '-ss', str(offset), '-t', str(chunk_len),
                    '-ar', '16000', '-ac', '1', chunk_file.name,
                ],
                check=True,
            )
            result = diarization_model_instance.diarize(audio=[chunk_file.name], batch_size=1)
            turns.extend(parse_diarization_segments(result, offset_seconds=offset, chunk_index=chunk_index))
        torch.cuda.empty_cache()
        offset += DIARIZATION_CHUNK_SECONDS
        chunk_index += 1

    return turns

@app.task
def process_job(job_id):
    with get_db_context() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "processing"

    try:
        with get_db_context() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            response = s3_client.get_object(
                Bucket=os.environ.get("MINIO_BUCKET"),
                Key=job.storage_path
            )
        file_bytes = response['Body'].read()

        with tempfile.NamedTemporaryFile(suffix=".webm") as raw_file, \
             tempfile.NamedTemporaryFile(suffix=".wav") as normalized_file:

            raw_file.write(file_bytes)
            raw_file.flush()

            subprocess.run(
                ['ffmpeg', '-y', '-i', raw_file.name, '-ar', '16000', '-ac', '1', normalized_file.name],
                check=True,
            )

            model = get_whisper_model()
            # vad_filter drops silence so segment timestamps line up with the
            # true audio duration instead of drifting/truncating on longer files.
            # word_timestamps=True is required for assign_text_to_turns to split
            # a segment across a speaker change rather than assigning the whole
            # segment to one speaker.
            segments_list, detected_language = transcribe_audio(model, normalized_file.name)
            full_text = " ".join(segment.text for segment in segments_list).strip()

            diarization_model_instance = get_diarization_model()
            parsed_turns = diarize_audio(diarization_model_instance, normalized_file.name)
            torch.cuda.empty_cache()

            titanet_model_instance = get_titanet_model()
            group_embeddings = build_diarization_group_embeddings(titanet_model_instance, normalized_file.name, parsed_turns)
            torch.cuda.empty_cache()

            group_to_label, clusters = cluster_diarization_groups(group_embeddings)
            relabeled_turns = [
                (start, end, group_to_label[(chunk_index, speaker_label)])
                for start, end, speaker_label, chunk_index in parsed_turns
            ]
            merged_turns = merge_adjacent_same_speaker_turns(relabeled_turns)
            turns_with_text = assign_text_to_turns(merged_turns, segments_list)

        # Best-effort: the LLM service being slow/unavailable shouldn't fail
        # an otherwise-successful transcription. Summary/entities just come
        # back empty in that case rather than the whole job erroring out.
        try:
            summary, entities = summarize_and_extract_entities(full_text)
        except Exception as exc:
            print(f"Summarization failed for job {job_id}: {exc}")
            summary, entities = None, []

        with get_db_context() as db:
            enrolled_speakers = [
                (speaker.id, speaker.name, speaker.embedding)
                for speaker in db.query(Speaker).filter(Speaker.status == "done").all()
            ]
        cluster_matches = match_clusters_to_enrolled_speakers(clusters, enrolled_speakers)

        with get_db_context() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            job.transcript = full_text
            job.detected_language = detected_language
            job.summary = summary
            job.entities = entities
            job.status = "done"
            for start_time, end_time, speaker_label, text in turns_with_text:
                matched_id, matched_name = cluster_matches.get(speaker_label, (None, None))
                db.add(Turn(
                    job_id=job_id,
                    start_time=start_time,
                    end_time=end_time,
                    speaker_label=matched_name or speaker_label,
                    text=text,
                    speaker_id=matched_id,
                ))
    except Exception as exc:
        with get_db_context() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            job.status = "failed"
            job.error_message = str(exc)[:2000]
        raise

@app.task
def enroll_speaker(speaker_id):
    try:
        with get_db_context() as db:
            speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
            response = s3_client.get_object(
                Bucket=os.environ.get("MINIO_BUCKET"),
                Key=speaker.storage_path
            )
        file_bytes = response['Body'].read()

        with tempfile.NamedTemporaryFile(suffix=".webm") as raw_file, \
             tempfile.NamedTemporaryFile(suffix=".wav") as normalized_file:

            raw_file.write(file_bytes)
            raw_file.flush()

            subprocess.run(
                ['ffmpeg', '-y', '-i', raw_file.name, '-ar', '16000', '-ac', '1', normalized_file.name],
                check=True,
            )

            titanet_model_instance = get_titanet_model()
            embedding = titanet_model_instance.get_embedding(normalized_file.name)
            torch.cuda.empty_cache()

        with get_db_context() as db:
            speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
            speaker.embedding = embedding.squeeze().cpu().numpy().tolist()
            speaker.status = "done"
    except Exception as exc:
        with get_db_context() as db:
            speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
            speaker.status = "failed"
            speaker.error_message = str(exc)[:2000]
        raise