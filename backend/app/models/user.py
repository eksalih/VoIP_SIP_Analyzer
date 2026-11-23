from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.db.database import Base

ROLES = ("admin", "supervisor", "user")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user", server_default="user")
    # Comma-separated extensions a normal user may see (admin/supervisor see everything)
    extensions = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    @property
    def extension_list(self) -> list[str]:
        return [e.strip() for e in (self.extensions or "").split(",") if e.strip()]
