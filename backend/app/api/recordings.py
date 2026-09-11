"""
Recordings API
Endpoints for retrieving and downloading reconstructed audio files.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.call import Call
from app.models.recording import Recording

logger = logging.getLogger(__name__)

router = APIRouter()

RECORDINGS_DIR = Path("data") / "recordings"


@router.get("/{call_id}")
async def get_call_recordings(
    call_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all recordings for a specific call.

    Returns list of recording metadata with download links.
    """
    result = await db.execute(
        select(Recording).where(Recording.call_id == call_id)
    )
    recordings = result.scalars().all()

    if not recordings:
        return {"call_id": call_id, "recordings": []}

    recording_data = []
    for rec in recordings:
        recording_data.append({
            "id": rec.id,
            "direction": rec.direction,
            "codec": rec.codec,
            "duration_seconds": rec.duration_seconds,
            "file_size_bytes": rec.file_size_bytes,
            "status": rec.status,
            "packets_used": rec.packets_used,
            "packets_missing": rec.packets_missing,
            "download_url": f"/recordings/download/{rec.id}",
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })

    return {
        "call_id": call_id,
        "recordings": recording_data,
    }


@router.get("/download/{recording_id}")
async def download_recording(
    recording_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Download a specific recording as a WAV file.
    """
    result = await db.execute(
        select(Recording).where(Recording.id == recording_id)
    )
    recording = result.scalar_one_or_none()

    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    if not recording.file_path:
        raise HTTPException(status_code=404, detail="Recording file path not set")

    # Reconstruct full path
    file_path = RECORDINGS_DIR / recording.file_path

    if not file_path.exists():
        logger.error(f"Recording file not found: {file_path}")
        raise HTTPException(status_code=404, detail="Recording file not found on disk")

    # Sanitize filename for download
    filename = f"call_{recording.call_id}_{recording.direction}.wav"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="audio/wav",
    )
