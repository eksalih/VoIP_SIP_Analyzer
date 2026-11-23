"""
Recording retention (v2.3.0).

Only the audio is removed. The call record, SIP events and quality metrics stay,
so history and analytics are unaffected; the call simply shows no recording.

  RECORDINGS_RETENTION_DAYS  delete recordings older than this (default 180, 0 = keep forever)
  RECORDINGS_MAX_GB          if the recordings exceed this size, delete the oldest first
                             until they fit (default 0 = no size limit)
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.call import Call, CallStatus
from app.services.audio_storage import remove_audio_files, resolve_audio_path

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    expired: int = 0       # removed because of age
    over_limit: int = 0    # removed because of the size cap
    freed_bytes: int = 0

    @property
    def removed(self) -> int:
        return self.expired + self.over_limit


def retention_settings() -> tuple[int, float]:
    def num(name, default):
        try:
            return float(os.getenv(name, default))
        except ValueError:
            logger.warning(f"Invalid {name}; using {default}")
            return float(default)

    return int(num("RECORDINGS_RETENTION_DAYS", 180)), num("RECORDINGS_MAX_GB", 0)


def _when(call: Call) -> datetime:
    return call.start_time or call.created_at or datetime.utcnow()


async def run_retention(
    session_factory: async_sessionmaker,
    days: Optional[int] = None,
    max_gb: Optional[float] = None,
    now: Optional[datetime] = None,
) -> RetentionResult:
    if days is None or max_gb is None:
        env_days, env_gb = retention_settings()
        days = env_days if days is None else days
        max_gb = env_gb if max_gb is None else max_gb
    now = now or datetime.utcnow()
    result = RetentionResult()

    async with session_factory() as db:
        calls = (await db.execute(
            select(Call).where(Call.audio_path.is_not(None), Call.status != CallStatus.IN_PROGRESS)
        )).scalars().all()
        calls.sort(key=_when)  # oldest first

        sizes: dict[int, int] = {}
        for c in calls:
            path = resolve_audio_path(c.audio_path)
            sizes[c.id] = os.path.getsize(path) if path else 0

        def drop(call: Call) -> None:
            remove_audio_files([call.audio_path])
            result.freed_bytes += sizes.get(call.id, 0)
            sizes[call.id] = 0
            call.audio_path = call.audio_codec = call.audio_duration = None

        remaining = []
        cutoff = now - timedelta(days=days) if days and days > 0 else None
        for c in calls:
            if cutoff and _when(c) < cutoff:
                drop(c)
                result.expired += 1
            else:
                remaining.append(c)

        if max_gb and max_gb > 0:
            limit = int(max_gb * 1024 ** 3)
            total = sum(sizes[c.id] for c in remaining)
            for c in remaining:
                if total <= limit:
                    break
                total -= sizes[c.id]
                drop(c)
                result.over_limit += 1

        await db.commit()

    if result.removed:
        logger.info(
            f"Retention removed {result.removed} recording(s) "
            f"({result.expired} expired, {result.over_limit} over size limit), "
            f"freed {result.freed_bytes / 1024 ** 2:.1f} MB"
        )
    return result
