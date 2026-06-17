import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.db.database import get_db
from app.models.test_run import TestRun
from app.services.pcap_service import process_pcap

router = APIRouter()


@router.post("")
async def replay_test(
    file: UploadFile = File(...),
    expected_status: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PCAP, specify expected call status, and get a PASS/FAIL report.
    """
    filename = file.filename or "replay.pcap"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pcap", ".pcapng", ".cap"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await process_pcap(
            file_path=tmp_path,
            filename=filename,
            db=db,
            expected_status=expected_status.upper(),
        )

        test_results = result.get("test_results", [])
        total = len(test_results)
        passed = sum(1 for r in test_results if r.get("result") == "PASS")
        failed = total - passed

        return {
            "file": filename,
            "expected_status": expected_status.upper(),
            "calls_tested": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round((passed / total * 100), 1) if total else 0,
            "results": test_results,
            "execution_time": result.get("execution_time"),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.get("/history")
async def get_test_history(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Get history of all replay test runs."""
    result = await db.execute(
        select(TestRun).order_by(TestRun.created_at.desc()).offset(skip).limit(limit)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "capture_file_name": r.capture_file_name,
            "expected_status": r.expected_status,
            "detected_status": r.detected_status,
            "result": r.result,
            "execution_time": r.execution_time,
            "created_at": r.created_at,
        }
        for r in runs
    ]
