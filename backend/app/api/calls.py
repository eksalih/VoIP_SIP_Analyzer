from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.db.database import get_db
from app.models.call import Call
from app.models.sip_event import SIPEvent
from app.schemas.schemas import CallSchema, CallDetailSchema, SIPEventSchema

router = APIRouter()


@router.get("", response_model=list[CallSchema])
async def list_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all calls with optional filters."""
    q = select(Call).order_by(Call.start_time.desc())

    if status:
        q = q.where(Call.status == status.upper())

    if search:
        q = q.where(
            (Call.caller.ilike(f"%{search}%")) |
            (Call.called.ilike(f"%{search}%")) |
            (Call.call_id.ilike(f"%{search}%"))
        )

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


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


@router.delete("/{call_id}")
async def delete_call(call_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a call and its events."""
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    await db.delete(call)
    return {"deleted": call_id}
