from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.database import Base


class RecordingStatus(str, enum.Enum):
    """Status of audio reconstruction attempt"""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"  # Some directions extracted, some failed
    FAILED = "FAILED"
    NO_RTP = "NO_RTP"


class Recording(Base):
    """
    Audio recording reconstructed from RTP payloads in a PCAP.
    One call can have multiple recordings (one per direction/codec combination).
    """
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False, index=True)

    # Recording metadata
    direction = Column(String, nullable=True)  # "inbound" | "outbound" | "both"
    codec = Column(String, nullable=True)  # e.g. "PCMU" (G.711 µ-law), "PCMA" (G.711 A-law)
    sample_rate = Column(Integer, default=8000)  # Hz (typically 8000 for VoIP)
    channels = Column(Integer, default=1)  # Mono

    # File information
    file_path = Column(String, nullable=True)  # Relative path to WAV file in recordings dir
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Reconstruction quality
    status = Column(SAEnum(RecordingStatus), default=RecordingStatus.FAILED, nullable=False)
    packets_used = Column(Integer, default=0)  # RTP packets included in final WAV
    packets_missing = Column(Integer, default=0)  # Gaps detected
    notes = Column(String, nullable=True)  # Error details or warnings

    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="recordings")
