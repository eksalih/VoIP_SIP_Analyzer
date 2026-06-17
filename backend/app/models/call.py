from sqlalchemy import Column, Integer, String, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.database import Base


class CallStatus(str, enum.Enum):
    ANSWERED = "ANSWERED"
    MISSED = "MISSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String, unique=True, index=True, nullable=False)
    caller = Column(String, nullable=True)
    called = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    source_ip = Column(String, nullable=True)
    destination_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    sip_domain = Column(String, nullable=True)
    branch_id = Column(String, nullable=True)

    start_time = Column(DateTime, nullable=True)
    ring_time = Column(DateTime, nullable=True)
    answer_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    ring_duration = Column(Float, nullable=True)
    talk_duration = Column(Float, nullable=True)
    total_duration = Column(Float, nullable=True)

    status = Column(SAEnum(CallStatus), default=CallStatus.UNKNOWN, nullable=False)
    sip_result_code = Column(Integer, nullable=True)
    rejection_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("SIPEvent", back_populates="call", cascade="all, delete-orphan")
    test_runs = relationship("TestRun", back_populates="call", cascade="all, delete-orphan")
