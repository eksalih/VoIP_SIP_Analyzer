"""
Live call persistence (v2.3.0).

Saves calls produced by the live tracker using the same helpers as the PCAP
upload path, so a live call looks identical to an uploaded one in the API and UI.

  * update():   open calls are stored with status IN_PROGRESS and refreshed as SIP arrives
  * finalize(): final status, SIP events, RTP quality metrics and (optionally) the recording
  * Each capture-service run is one CaptureFile of kind "live", so live calls group
    like uploads and the existing file-level counts keep working.

SIP events are written at finalisation only (rewriting them on every packet
would be wasteful), so an in-progress call has no event list yet.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, exists, func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capture.rtp_spool import SpoolData
from app.core.call_state_machine import CallSession
from app.core.rtp_analyzer import compute_call_metrics
from app.models.call import Call, CallStatus
from app.models.capture_file import CaptureFile
from app.models.rtp_stream import RTPStream
from app.models.sip_event import SIPEvent
from app.services.pcap_service import (
    _save_events, _save_rtp_streams, _upsert_call, write_call_audio,
)

logger = logging.getLogger(__name__)

_COUNT_FIELDS = {
    CallStatus.ANSWERED: "answered_count",
    CallStatus.MISSED: "missed_count",
    CallStatus.REJECTED: "rejected_count",
    CallStatus.FAILED: "failed_count",
    CallStatus.CANCELLED: "cancelled_count",
}


class LiveCallStore:
    def __init__(self, session_factory: async_sessionmaker, record_audio: bool = True):
        self._session_factory = session_factory
        self.record_audio = record_audio

    # ── capture runs ──────────────────────────────────────────────────────
    async def start_run(self, label: Optional[str] = None) -> int:
        """Create the CaptureFile that groups every call of this capture-service run."""
        async with self._session_factory() as db:
            run = CaptureFile(
                filename=f"Live capture {datetime.now():%Y-%m-%d %H:%M:%S}",
                kind="live",
                label=label,
            )
            db.add(run)
            await db.commit()
            return run.id

    async def end_run(self, run_id: Optional[int]) -> None:
        """Update the run's counts; a run that never saw a call is removed, not left as an empty entry."""
        if run_id is None:
            return
        async with self._session_factory() as db:
            await self._refresh_counts(db, run_id)
            await db.commit()
        await self.purge_empty_runs()

    async def purge_empty_runs(self) -> int:
        """Remove live capture runs that contain no calls (left by earlier starts and restarts)."""
        async with self._session_factory() as db:
            result = await db.execute(
                delete(CaptureFile).where(
                    CaptureFile.kind == "live",
                    ~exists().where(Call.capture_file_id == CaptureFile.id),
                )
            )
            await db.commit()
            return result.rowcount or 0

    async def recover_orphans(self) -> int:
        """Calls left IN_PROGRESS by a crashed or killed earlier run can never finish; mark them UNKNOWN."""
        async with self._session_factory() as db:
            result = await db.execute(
                sql_update(Call)
                .where(Call.source == "live", Call.status == CallStatus.IN_PROGRESS)
                .values(status=CallStatus.UNKNOWN)
            )
            await db.commit()
            count = result.rowcount or 0
        if count:
            logger.warning(f"Marked {count} unfinished live call(s) from a previous run as UNKNOWN")
        return count

    # ── calls ─────────────────────────────────────────────────────────────
    async def update(self, run_id: int, session: CallSession) -> int:
        """Create or refresh a call that is still in progress. Returns the call's database id."""
        async with self._session_factory() as db:
            call = await _upsert_call(
                session, run_id, db, source="live", status_override=CallStatus.IN_PROGRESS
            )
            await db.commit()
            return call.id

    async def finalize(
        self,
        run_id: int,
        session: CallSession,
        spool: Optional[SpoolData] = None,
    ) -> int:
        """Store the call's final state plus events, media quality and recording. Returns its id."""
        async with self._session_factory() as db:
            call = await _upsert_call(session, run_id, db, source="live")

            # Idempotent: finalising twice must not duplicate children
            await db.execute(delete(SIPEvent).where(SIPEvent.call_id == call.id))
            await db.execute(delete(RTPStream).where(RTPStream.call_id == call.id))
            await _save_events(session, call, db)

            if spool and spool.total_packets:
                try:
                    metrics = compute_call_metrics(
                        spool.a2b, spool.b2a, spool.ptime_ms, label=session.call_id
                    )
                    if metrics:
                        await _save_rtp_streams(metrics, call, db)
                except Exception as e:
                    logger.warning(f"Media metrics failed for {session.call_id} (non-fatal): {e}")

                if self.record_audio:
                    write_call_audio(call, spool.a2b, spool.b2a)

            await db.flush()
            await self._refresh_counts(db, run_id)
            await db.commit()
            return call.id

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    async def _refresh_counts(db: AsyncSession, run_id: int) -> None:
        """Recompute the run's summary counts from its finalised calls."""
        run = await db.get(CaptureFile, run_id)
        if run is None:
            return
        rows = await db.execute(
            select(Call.status, func.count(Call.id))
            .where(Call.capture_file_id == run_id, Call.status != CallStatus.IN_PROGRESS)
            .group_by(Call.status)
        )
        counts = {status: n for status, n in rows.all()}
        for status, field in _COUNT_FIELDS.items():
            setattr(run, field, counts.get(status, 0))
        run.calls_found = sum(counts.values())
