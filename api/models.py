from sqlalchemy import DateTime, Text, String, Column, Uuid
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