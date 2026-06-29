from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base


class RTPStream(Base):
    """
    One directional RTP media stream associated with an answered call.
    A normal call has two rows (one per direction).
    One-way audio is detected when only one direction has packets.
    """
    __tablename__ = "rtp_streams"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False, index=True)

    # Network endpoints
    source_ip = Column(String, nullable=True)
    source_port = Column(Integer, nullable=True)
    destination_ip = Column(String, nullable=True)
    destination_port = Column(Integer, nullable=True)

    # RTP stream identity
    ssrc = Column(String, nullable=True)         # hex string e.g. "0x30e21ba4"
    payload_type = Column(Integer, nullable=True)
    codec = Column(String, nullable=True)        # e.g. "PCMU/8000", "PCMA/8000"

    # Packet counts
    packet_count = Column(Integer, default=0)
    expected_packets = Column(Integer, nullable=True)

    # Quality metrics
    packet_loss_count = Column(Integer, default=0)
    packet_loss_pct = Column(Float, nullable=True)   # 0.0–100.0
    jitter_ms = Column(Float, nullable=True)         # mean inter-arrival jitter
    jitter_max_ms = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # One-way audio: True if the other direction has zero packets
    is_one_way = Column(Boolean, default=False)

    call = relationship("Call", back_populates="rtp_streams")
