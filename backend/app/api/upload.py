import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends
from fastapi import HTTPException
from typing import Optional

from app.db.database import get_db
from app.services.pcap_service import process_pcap, process_pcap_batch
from app.schemas.schemas import UploadResponseSchema, BatchUploadResponseSchema
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

ALLOWED_EXTENSIONS = {".pcap", ".pcapng", ".cap"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB per file
MAX_BATCH_FILES = 25


def _validate_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext} ({filename}). Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    return ext


@router.post("", response_model=UploadResponseSchema)
async def upload_pcap(
    file: UploadFile = File(...),
    expected_status: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a single PCAP/PCAPNG file for analysis."""
    filename = file.filename or "capture.pcap"
    ext = _validate_extension(filename)

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
            file_size_bytes=len(content),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/batch", response_model=BatchUploadResponseSchema)
async def upload_pcap_batch(
    files: list[UploadFile] = File(...),
    expected_status: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload multiple PCAP/PCAPNG files in one request.
    Each file becomes its own capture file entry; one bad file does not
    block the rest of the batch from processing.
    """
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files in one batch (max {MAX_BATCH_FILES}).",
        )

    # Validate extensions up front so we fail fast before writing any temp files
    for f in files:
        _validate_extension(f.filename or "capture.pcap")

    tmp_entries: list[tuple[str, str, int]] = []
    try:
        for f in files:
            filename = f.filename or "capture.pcap"
            ext = os.path.splitext(filename)[1].lower()
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max 200MB): {filename}",
                )
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_entries.append((tmp.name, filename, len(content)))

        result = await process_pcap_batch(
            files=tmp_entries,
            db=db,
            expected_status=expected_status,
        )
        return result
    finally:
        for tmp_path, _, _ in tmp_entries:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
