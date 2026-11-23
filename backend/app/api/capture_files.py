from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.api.auth import require
from app.db.database import get_db
from app.models.user import User
from app.services import audit
from app.models.call import Call
from app.models.capture_file import CaptureFile
from app.schemas.schemas import CaptureFileSchema
from app.services.audio_storage import remove_audio_files

router = APIRouter()


class CaptureFilePatch(BaseModel):
    label: Optional[str] = None


@router.get("", response_model=list[CaptureFileSchema])
async def list_capture_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded capture files, most recent first."""
    q = (
        select(CaptureFile)
        .order_by(CaptureFile.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{capture_file_id}", response_model=CaptureFileSchema)
async def get_capture_file(capture_file_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single capture file's metadata and summary counts."""
    result = await db.execute(select(CaptureFile).where(CaptureFile.id == capture_file_id))
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Capture file not found")
    return cf


@router.patch("/{capture_file_id}", response_model=CaptureFileSchema)
async def update_capture_file(
    capture_file_id: int,
    body: CaptureFilePatch,
    db: AsyncSession = Depends(get_db),
):
    """Update a capture file's label. Pass null to clear the label."""
    result = await db.execute(select(CaptureFile).where(CaptureFile.id == capture_file_id))
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Capture file not found")
    # Explicitly allow clearing (null) as well as setting a new label
    cf.label = body.label.strip() if body.label and body.label.strip() else None
    await db.flush()
    return cf


@router.delete("/{capture_file_id}")
async def delete_capture_file(request: Request, capture_file_id: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(require("calls.delete"))):
    """Delete a capture file and all calls/events derived from it."""
    result = await db.execute(select(CaptureFile).where(CaptureFile.id == capture_file_id))
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Capture file not found")
    # Collect saved recordings before the calls are gone, then remove the files.
    audio_paths = (await db.execute(
        select(Call.audio_path).where(
            Call.capture_file_id == capture_file_id, Call.audio_path.isnot(None)
        )
    )).scalars().all()
    await db.delete(cf)
    await db.flush()
    remove_audio_files(audio_paths)
    await audit.record(db, user, "capture_file.delete", request=request, detail=f"id {capture_file_id}")
    return {"deleted": capture_file_id}
