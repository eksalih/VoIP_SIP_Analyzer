from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base


class SIPEvent(Base):
    __tablename__ = "sip_events"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=True)
    sip_method = Column(String, nullable=True)
    sip_response_code = Column(Integer, nullable=True)
    sip_response_text = Column(String, nullable=True)
    source_ip = Column(String, nullable=True)
    destination_ip = Column(String, nullable=True)
    raw_message = Column(Text, nullable=True)
    sequence_number = Column(Integer, nullable=True)

    call = relationship("Call", back_populates="events")
