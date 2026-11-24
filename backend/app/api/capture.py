"""Capture service status (v2.3.0)."""
from fastapi import APIRouter

from app.capture.status import read_status

router = APIRouter()


@router.get("/status")
async def capture_status():
    """
    state is one of: running, stopped, stale (no heartbeat: service died or hung),
    not_configured (the capture service has never reported in).
    """
    return read_status()
