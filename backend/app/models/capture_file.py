from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class CaptureFile(Base):
    """
    Represents one uploaded PCAP/PCAPNG file.
    Groups all calls extracted from that file so multiple test sessions
    (or multiple files within one session) never blur together in the call list.
    """
    __tablename__ = "capture_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)

    packets_parsed = Column(Integer, default=0)
    calls_found = Column(Integer, default=0)

    # Quick summary counts for the file-grouped list view, avoids a join+count on every list render
    answered_count = Column(Integer, default=0)
    missed_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    cancelled_count = Column(Integer, default=0)

    processing_time_seconds = Column(Float, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Optional free-text label so a tester can tag a file ("3CX firmware 18.2 retest")
    label = Column(String, nullable=True)

    calls = relationship("Call", back_populates="capture_file", cascade="all, delete-orphan")
