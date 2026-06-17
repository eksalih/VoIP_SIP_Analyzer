import os
import aiofiles
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends
from fastapi import HTTPException
from typing import Optional

from app.db.database import get_db
from app.services.pcap_service import process_pcap
from app.schemas.schemas import UploadResponseSchema
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

ALLOWED_EXTENSIONS = {".pcap", ".pcapng", ".cap"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB


@router.post("", response_model=UploadResponseSchema)
async def upload_pcap(
    file: UploadFile = File(...),
    expected_status: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PCAP/PCAPNG file for analysis."""
    filename = file.filename or "capture.pcap"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 200MB)")
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await process_pcap(
            file_path=tmp_path,
            filename=filename,
            db=db,
            expected_status=expected_status,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
