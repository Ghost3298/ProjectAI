from fastapi import FastAPI
from db import Base, engine
from models import Job
from storage import ensure_bucket_exists
import os

app = FastAPI()

Base.metadata.create_all(bind=engine)
ensure_bucket_exists(os.environ.get('MINIO_BUCKET'))

@app.get("/health", status_code=200)
def is_healthy():
    return {"status" : "ok"}