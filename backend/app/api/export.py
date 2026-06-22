from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone
import io

from app.db.database import get_db
from app.services.export_service import generate_csv, generate_pdf

router = APIRouter()


def _safe_filename(base: str, ext: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{base}_{ts}.{ext}"


@router.get("/csv")
async def export_csv(
    capture_file_id: Optional[int] = Query(None, description="Filter to a single capture file"),
    db: AsyncSession = Depends(get_db),
):
    """
    Download all calls (or one capture file's calls) as a CSV file.
    """
    csv_bytes = await generate_csv(db, capture_file_id=capture_file_id)
    filename = _safe_filename(
        f"sip_calls_cf{capture_file_id}" if capture_file_id else "sip_calls_all",
        "csv",
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf")
async def export_pdf(
    capture_file_id: Optional[int] = Query(None, description="Filter to a single capture file"),
    vendor_name: str = Query("", description="Vendor / PBX name to include on the report cover"),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a PDF compatibility report (printable, suitable for vendor sign-off).
    """
    pdf_bytes = await generate_pdf(
        db,
        capture_file_id=capture_file_id,
        vendor_name=vendor_name,
    )
    filename = _safe_filename(
        f"sip_report_cf{capture_file_id}" if capture_file_id else "sip_report_all",
        "pdf",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
