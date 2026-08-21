from celery import Celery
import os, time
from models import Job
from db import get_db_context
from storage import s3_client 
from faster_whisper import WhisperModel
import tempfile

app = Celery(
    'tasks',
    broker=os.environ.get('CELERY_BROKER_URL'),
    backend=os.environ.get('CELERY_RESULT_BACKEND')
)

whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = WhisperModel("small", device="cuda", compute_type="float16")
    return whisper_model

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

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(file_bytes)
            tmp.flush()

            model = get_whisper_model()
            segments, info = model.transcribe(tmp.name)
            # add , language="ar" after tmp.name if we want all the recordings to show in arabic
            full_text = " ".join(segment.text for segment in segments)

        job.transcript = full_text
        job.status = "done"