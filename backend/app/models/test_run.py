from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=True, index=True)
    capture_file_name = Column(String, nullable=False)
    expected_status = Column(String, nullable=True)
    detected_status = Column(String, nullable=True)
    result = Column(String, nullable=True)  # PASS / FAIL / N/A
    execution_time = Column(Float, nullable=True)
    notes = Column(String, nullable=True)
    passed = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="test_runs")
