from fastapi import Depends, FastAPI, Form, UploadFile, HTTPException
from pydantic import BaseModel
from db import Base, engine, get_db
from models import Job, Turn, Speaker, RecordingSession, SessionNote
from storage import ensure_bucket_exists, s3_client
from sqlalchemy.orm import Session
import os
import uuid
from celery_app import process_job, enroll_speaker
from fastapi.middleware.cors import CORSMiddleware

class RenameSessionRequest(BaseModel):
    name: str

class CreateNoteRequest(BaseModel):
    text: str

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
ensure_bucket_exists(os.environ.get('MINIO_BUCKET'))

@app.get("/health", status_code=200)
def is_healthy():
    return {"status" : "ok"}

def summarize_job_statuses(statuses):
    if not statuses:
        return "empty"
    if any(s in ("queued", "processing") for s in statuses):
        return "processing"
    if any(s == "failed" for s in statuses):
        return "failed"
    return "done"

@app.post("/sessions")
def create_session(db: Session = Depends(get_db)):
    new_session = RecordingSession(id = uuid.uuid4())
    db.add(new_session)
    db.commit()

    return {"session_id": str(new_session.id)}

@app.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(RecordingSession).order_by(RecordingSession.created_at.desc()).all()

    result = []
    for session in sessions:
        jobs = db.query(Job).filter(Job.session_id == session.id).all()
        languages = [job.detected_language for job in jobs if job.detected_language]
        result.append({
            "session_id": str(session.id),
            "name": session.name,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "recording_count": len(jobs),
            "status": summarize_job_statuses([job.status for job in jobs]),
            "detected_language": languages[0] if languages else None,
            "first_recording_name": jobs[0].original_filename if jobs else None,
        })
    return result

@app.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameSessionRequest, db: Session = Depends(get_db)):
    session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.name = body.name.strip() or None
    db.commit()

    return {"session_id": str(session.id), "name": session.name}

@app.post("/sessions/{session_id}/notes")
def create_note(session_id: str, body: CreateNoteRequest, db: Session = Depends(get_db)):
    session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Note text is empty")

    new_note = SessionNote(id = uuid.uuid4(), session_id = session_id, text = text)
    db.add(new_note)
    db.commit()

    return {
        "note_id": str(new_note.id),
        "text": new_note.text,
        "created_at": new_note.created_at.isoformat() if new_note.created_at else None,
    }

@app.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    jobs = db.query(Job).filter(Job.session_id == session_id).order_by(Job.created_at).all()
    notes = db.query(SessionNote).filter(SessionNote.session_id == session_id).order_by(SessionNote.created_at).all()

    job_payloads = []
    for job in jobs:
        turns = db.query(Turn).filter(Turn.job_id == job.id).order_by(Turn.start_time).all()
        job_payloads.append({
            "job_id": str(job.id),
            "original_filename": job.original_filename,
            "status": job.status,
            "transcript": job.transcript,
            "detected_language": job.detected_language,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "turns": [
                {
                    "start_time": turn.start_time,
                    "end_time": turn.end_time,
                    "speaker_label": turn.speaker_label,
                    "text": turn.text,
                    "speaker_id": str(turn.speaker_id) if turn.speaker_id else None,
                }
                for turn in turns
            ],
        })

    return {
        "session_id": str(session.id),
        "name": session.name,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "jobs": job_payloads,
        "notes": [
            {
                "note_id": str(note.id),
                "text": note.text,
                "created_at": note.created_at.isoformat() if note.created_at else None,
            }
            for note in notes
        ],
    }

@app.post("/jobs")
async def create_job(file: UploadFile, session_id: str = Form(None), db: Session = Depends(get_db)):
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
        session_id = session_id,
        status = "queued",
        original_filename = file.filename,
        storage_path = storage_path
    )

    db.add(new_job)
    db.commit()

    process_job.delay(str(job_id))

    return {"job_id": str(job_id)}

@app.post("/speakers")
async def create_speaker(file: UploadFile, name: str = Form(...), db: Session = Depends(get_db)):
    speaker_id = uuid.uuid4()
    contents = await file.read()

    storage_path = f"speakers/{speaker_id}/{file.filename}"
    s3_client.put_object(
        Bucket = os.environ.get('MINIO_BUCKET'),
        Key = storage_path,
        Body = contents,
    )

    new_speaker = Speaker(
        id = speaker_id,
        name = name,
        status = "processing",
        storage_path = storage_path
    )

    db.add(new_speaker)
    db.commit()

    enroll_speaker.delay(str(speaker_id))

    return {"speaker_id": str(speaker_id)}

@app.delete("/speakers/{speaker_id}")
def delete_speaker(speaker_id: str, db: Session = Depends(get_db)):
    speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()

    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found")

    db.query(Turn).filter(Turn.speaker_id == speaker.id).update({Turn.speaker_id: None})

    s3_client.delete_object(
        Bucket = os.environ.get('MINIO_BUCKET'),
        Key = speaker.storage_path,
    )

    db.delete(speaker)
    db.commit()

    return {"speaker_id": speaker_id}

@app.get("/speakers")
def list_speakers(db: Session = Depends(get_db)):
    speakers = db.query(Speaker).order_by(Speaker.created_at.desc()).all()

    return [
        {
            "speaker_id": str(speaker.id),
            "name": speaker.name,
            "status": speaker.status,
            "created_at": speaker.created_at.isoformat() if speaker.created_at else None,
        }
        for speaker in speakers
    ]

@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    turns = db.query(Turn).filter(Turn.job_id == job.id).order_by(Turn.start_time).all()

    return{
        "job_id" : str(job.id),
        "status" : job.status,
        "transcript" : job.transcript,
        "detected_language" : job.detected_language,
        "error_message" : job.error_message,
        "created_at" : job.created_at.isoformat() if job.created_at else None,
        "turns" : [
            {
                "start_time": turn.start_time,
                "end_time": turn.end_time,
                "speaker_label": turn.speaker_label,
                "text": turn.text,
                "speaker_id": str(turn.speaker_id) if turn.speaker_id else None,
            }
            for turn in turns
        ]
    }
