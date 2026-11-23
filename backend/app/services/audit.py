"""Append-only audit trail for sensitive actions (recording playback/download, deletes, logins)."""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def record(db: AsyncSession, user, action: str, call_id: Optional[int] = None,
                 request=None, detail: Optional[str] = None, username: Optional[str] = None) -> None:
    """Write one audit row and commit it immediately so it survives later failures."""
    ip = request.client.host if request is not None and request.client else None
    db.add(AuditLog(
        user_id=getattr(user, "id", None),
        username=getattr(user, "username", None) or username,
        action=action, call_id=call_id, ip=ip, detail=detail,
    ))
    await db.commit()
