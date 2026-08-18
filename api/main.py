from fastapi import Depends, FastAPI, UploadFile
from db import Base, engine, get_db
from models import Job
from storage import ensure_bucket_exists, s3_client
from sqlalchemy.orm import Session
import os
import uuid

app = FastAPI()

Base.metadata.create_all(bind=engine)
ensure_bucket_exists(os.environ.get('MINIO_BUCKET'))

@app.get("/health", status_code=200)
def is_healthy():
    return {"status" : "ok"}

@app.post("/jobs")
async def create_job(file: UploadFile, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    contents = await file.read()

    storage_path = f"{job_id}/{file.filename}"
    s3_client.put_object(
        Bucket = os.environ.get('MINIO_BUCKET'),
        Key = storage_path,
        Body = contents,
    )

    new_job = Job(
        id = job_id,
        status = "queued",
        original_filename = file.filename,
        storage_path = storage_path
    )
    db.add(new_job)
    db.commit()

    return {"job_id": str(job_id)}

    