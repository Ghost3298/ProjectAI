from sqlalchemy import DateTime, Text, String, Column, Uuid, ForeignKey, Float
from sqlalchemy.sql import func
from db import Base
import uuid

class Job(Base):
    __tablename__ = "jobs"

    id = Column(
        Uuid(as_uuid=True),
        primary_key= True,
        default= uuid.uuid4,
        server_default= func.gen_random_uuid()
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

    storage_path = Column(
        String,
        nullable= False
    )

    transcript = Column(
        Text
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

    speaker_id = Column(
        Uuid(as_uuid=True),
        nullable=True
    )