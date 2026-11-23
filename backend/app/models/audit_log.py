from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.database import Base


class AuditLog(Base):
    """Who did what. Rows are append-only; user_id/username are copied so history survives user deletion."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)   # recording.play, recording.download, login, ...
    call_id = Column(Integer, nullable=True, index=True)
    ip = Column(String, nullable=True)
    detail = Column(String, nullable=True)
