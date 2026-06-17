from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date

from app.db.database import get_db
from app.models.call import Call, CallStatus
from app.schemas.schemas import AnalyticsSchema

router = APIRouter()


@router.get("", response_model=AnalyticsSchema)
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """Return aggregate analytics for all calls."""
    total_q = await db.execute(select(func.count(Call.id)))
    total = total_q.scalar() or 0

    def _count(status: CallStatus):
        return select(func.count(Call.id)).where(Call.status == status)

    answered = (await db.execute(_count(CallStatus.ANSWERED))).scalar() or 0
    missed = (await db.execute(_count(CallStatus.MISSED))).scalar() or 0
    rejected = (await db.execute(_count(CallStatus.REJECTED))).scalar() or 0
    failed = (await db.execute(_count(CallStatus.FAILED))).scalar() or 0
    cancelled = (await db.execute(_count(CallStatus.CANCELLED))).scalar() or 0

    avg_ring_q = await db.execute(
        select(func.avg(Call.ring_duration)).where(Call.ring_duration.isnot(None))
    )
    avg_ring = avg_ring_q.scalar()

    avg_talk_q = await db.execute(
        select(func.avg(Call.talk_duration)).where(Call.talk_duration.isnot(None))
    )
    avg_talk = avg_talk_q.scalar()

    success_rate = round((answered / total * 100), 1) if total else 0.0

    # Calls per day (last 30 days)
    days_q = await db.execute(
        select(
            func.date(Call.start_time).label("day"),
            func.count(Call.id).label("count"),
        )
        .where(Call.start_time.isnot(None))
        .group_by(func.date(Call.start_time))
        .order_by(func.date(Call.start_time).desc())
        .limit(30)
    )
    calls_by_day = [{"date": str(r.day), "count": r.count} for r in days_q]
    calls_by_day.reverse()

    status_distribution = [
        {"status": "ANSWERED", "count": answered, "color": "#4caf50"},
        {"status": "MISSED", "count": missed, "color": "#ff9800"},
        {"status": "REJECTED", "count": rejected, "color": "#f44336"},
        {"status": "FAILED", "count": failed, "color": "#9e9e9e"},
        {"status": "CANCELLED", "count": cancelled, "color": "#2196f3"},
    ]

    return AnalyticsSchema(
        total_calls=total,
        answered=answered,
        missed=missed,
        rejected=rejected,
        failed=failed,
        cancelled=cancelled,
        success_rate=success_rate,
        avg_ring_duration=round(avg_ring, 2) if avg_ring else None,
        avg_talk_duration=round(avg_talk, 2) if avg_talk else None,
        calls_by_day=calls_by_day,
        status_distribution=status_distribution,
    )
