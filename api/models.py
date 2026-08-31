from sqlalchemy import DateTime, Text, String, Column, Uuid, ForeignKey, Float
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func
from db import Base
import uuid

class RecordingSession(Base):
    __tablename__ = "sessions"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()
    )

    name = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class SessionNote(Base):
    __tablename__ = "session_notes"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()
    )

    session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False
    )

    text = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class Job(Base):
    __tablename__ = "jobs"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()
    )

    session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=True
    )

    status = Column(
        String,
        nullable=False
    )

    original_filename = Column(
        String,
        nullable=False,
        index= True
    )

    name = Column(
        String,
        nullable=True
    )

    storage_path = Column(
        String,
        nullable= False
    )

    transcript = Column(
        Text
    )

    detected_language = Column(
        String,
        nullable=True
    )

    summary = Column(
        Text,
        nullable=True
    )

    entities = Column(
        JSONB,
        nullable=True
    )

    error_message = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class Translation(Base):
    __tablename__ = "translations"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()   
    )

    job_id = Column(
        Uuid(as_uuid=True), 
        ForeignKey("jobs.id"), 
        nullable=False
    )

    language = Column(
        String,
        nullable = False,  
    )

    translated_text = Column(
        Text, nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

class Speaker(Base):
    __tablename__ = "speakers"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()
    )

    name = Column(
        String,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    storage_path = Column(
        String,
        nullable=False
    )

    embedding = Column(
        ARRAY(Float),
        nullable=True
    )

    error_message = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class Turn(Base):
    __tablename__ = "turns"

    id = Column(
            Uuid(as_uuid=True),
            primary_key= True,
            default= uuid.uuid4,
            server_default= func.gen_random_uuid()   
        )

    job_id = Column(
            Uuid(as_uuid=True), 
            ForeignKey("jobs.id"), 
            nullable=False
        )

    start_time = Column(
        Float,
        nullable=False
    )

    end_time = Column(
        Float,
        nullable=False
    )

    speaker_label = Column(
        String,
        nullable=False
    )

    text = Column(
        Text,
        nullable=True
    )

    speaker_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("speakers.id"),
        nullable=True
    )