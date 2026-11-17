from sqlalchemy import Column, Integer, String, Float, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint
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
    __table_args__ = (
        # SIP Call-IDs only need to be unique *within* a single capture file.
        # Different test sessions/phones can legitimately reuse the same Call-ID
        # string, so a global unique constraint would corrupt bulk uploads.
        UniqueConstraint("capture_file_id", "call_id", name="uq_call_per_capture_file"),
    )

    id = Column(Integer, primary_key=True, index=True)
    capture_file_id = Column(Integer, ForeignKey("capture_files.id"), nullable=True, index=True)
    call_id = Column(String, index=True, nullable=False)
    caller = Column(String, nullable=True)
    called = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    source_ip = Column(String, nullable=True)
    destination_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    vendor = Column(String, nullable=True)            # detected from user_agent, e.g. "Yeastar"
    vendor_category = Column(String, nullable=True)   # "pbx" | "phone" | "softphone"
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

    # Reconstructed call audio (v2.2.0, opt-in via SAVE_CALL_AUDIO). Path is relative
    # to the recordings directory so the data folder stays relocatable.
    audio_path = Column(String, nullable=True)
    audio_codec = Column(String, nullable=True)
    audio_duration = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_path)

    capture_file = relationship("CaptureFile", back_populates="calls")
    events = relationship("SIPEvent", back_populates="call", cascade="all, delete-orphan")
    test_runs = relationship("TestRun", back_populates="call", cascade="all, delete-orphan")
    rtp_streams = relationship("RTPStream", back_populates="call", cascade="all, delete-orphan")
