import subprocess
from celery import Celery
import os, time
from models import Job, Turn
from db import get_db_context
from storage import s3_client 
from faster_whisper import WhisperModel
import tempfile
from nemo.collections.asr.models import SortformerEncLabelModel

app = Celery(
    'tasks',
    broker=os.environ.get('CELERY_BROKER_URL'),
    backend=os.environ.get('CELERY_RESULT_BACKEND')
)

whisper_model = None
diarization_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = WhisperModel("small", device="cuda", compute_type="float16")
    return whisper_model

def get_diarization_model():
    global diarization_model
    if diarization_model is None:
        diarization_model = SortformerEncLabelModel.from_pretrained('nvidia/diar_sortformer_4spk-v1')
    return diarization_model

@app.task
def add(x, y):
    time.sleep(5)
    return x + y

@app.task
def process_job(job_id):
    with get_db_context() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "processing"

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
                check = True,
            )

            model = get_whisper_model()
            segments, info = model.transcribe(normalized_file.name)
            # add , language="ar" after tmp.name if we want all the recordings to show in arabic
            full_text = " ".join(segment.text for segment in segments)

            segments_list = list(model.transcribe(normalized_file.name)[0])
            full_text = " ".join(segment.text for segment in segments_list)
            if segments_list:
                print(f"Whisper produced {len(segments_list)} segments, last one ends at {segments_list[-1].end}s")
                
            diarization_model_instance = get_diarization_model()
            diarization_result  = diarization_model_instance.diarize(audio=[normalized_file.name], batch_size=1)

            for segment_str in diarization_result[0]:
                start_str, end_str, speaker_label = segment_str.split()
                new_turn = Turn(
                    job_id = job_id,
                    start_time = float(start_str),
                    end_time = float(end_str),
                    speaker_label = speaker_label
                )
                db.add(new_turn)
            
        job.transcript = full_text
        job.status = "done"