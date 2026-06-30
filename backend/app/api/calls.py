from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Optional

from app.db.database import get_db
from app.models.call import Call
from app.models.sip_event import SIPEvent
from app.models.test_run import TestRun
from app.models.capture_file import CaptureFile
from app.models.rtp_stream import RTPStream
from app.schemas.schemas import CallSchema, CallDetailSchema, SIPEventSchema, RTPStreamSchema

router = APIRouter()


@router.get("", response_model=list[CallSchema])
async def list_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    capture_file_id: Optional[int] = Query(None, description="Filter to calls from a single uploaded capture file"),
    vendor: Optional[str] = Query(None, description="Filter to calls from a detected vendor, e.g. Yeastar"),
    db: AsyncSession = Depends(get_db),
):
    """List all calls with optional filters."""
    q = select(Call).order_by(Call.start_time.desc())

    if status:
        q = q.where(Call.status == status.upper())

    if capture_file_id is not None:
        q = q.where(Call.capture_file_id == capture_file_id)

    if vendor:
        q = q.where(Call.vendor == vendor)

    if search:
        q = q.where(
            (Call.caller.ilike(f"%{search}%")) |
            (Call.called.ilike(f"%{search}%")) |
            (Call.call_id.ilike(f"%{search}%"))
        )

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.delete("/clear-all")
async def clear_all_data(
    confirm: bool = Query(False, description="Must be true to actually clear data"),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete ALL calls, SIP events, test runs, and capture file records.
    Use this between test sessions so old captures don't mix with new ones.
    Requires confirm=true to actually execute (safety guard against accidental calls).
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to permanently clear all call data.",
        )

    calls_count = (await db.execute(select(func.count(Call.id)))).scalar() or 0
    events_count = (await db.execute(select(func.count(SIPEvent.id)))).scalar() or 0
    tests_count = (await db.execute(select(func.count(TestRun.id)))).scalar() or 0
    files_count = (await db.execute(select(func.count(CaptureFile.id)))).scalar() or 0

    # Delete children first (SIPEvent/TestRun reference Call; Call references CaptureFile).
    await db.execute(delete(SIPEvent))
    await db.execute(delete(TestRun))
    await db.execute(delete(Call))
    await db.execute(delete(CaptureFile))
    await db.commit()

    return {
        "status": "ok",
        "message": "All call data cleared.",
        "deleted": {
            "calls": calls_count,
            "events": events_count,
            "test_runs": tests_count,
            "capture_files": files_count,
        },
    }


@router.get("/{call_id}", response_model=CallDetailSchema)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single call with all SIP events."""
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    events_result = await db.execute(
        select(SIPEvent)
        .where(SIPEvent.call_id == call.id)
        .order_by(SIPEvent.timestamp)
    )
    call.events = events_result.scalars().all()
    return call


@router.get("/{call_id}/events", response_model=list[SIPEventSchema])
async def get_call_events(call_id: int, db: AsyncSession = Depends(get_db)):
    """Get all SIP events for a call."""
    result = await db.execute(
        select(SIPEvent)
        .where(SIPEvent.call_id == call_id)
        .order_by(SIPEvent.timestamp)
    )
    return result.scalars().all()


@router.get("/{call_id}/media", response_model=list[RTPStreamSchema])
async def get_call_media(call_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get RTP media quality metrics for a call.
    Returns an empty list for MISSED/REJECTED/CANCELLED calls,
    or for captures that don't include RTP alongside SIP signaling.
    """
    result = await db.execute(
        select(RTPStream).where(RTPStream.call_id == call_id)
    )
    return result.scalars().all()


@router.delete("/{call_id}")
async def delete_call(call_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a call and its events."""
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    await db.delete(call)
    return {"deleted": call_id}
