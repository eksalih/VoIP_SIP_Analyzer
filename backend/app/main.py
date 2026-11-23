from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
from contextlib import asynccontextmanager

from app.db.database import init_db, AsyncSessionLocal
from app.services.retention import retention_loop
from app.api import calls, analytics, upload, health, replay, capture_files, export


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(
        retention_loop(AsyncSessionLocal, float(os.getenv("RETENTION_INTERVAL_SECONDS", 3600)))
    )
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="VoIP SIP Analyzer",
    description="SIP packet capture analysis and call validation platform",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(upload.router, prefix="/upload-pcap", tags=["Upload"])
app.include_router(calls.router, prefix="/calls", tags=["Calls"])
app.include_router(capture_files.router, prefix="/capture-files", tags=["Capture Files"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(replay.router, prefix="/replay-test", tags=["Replay"])
app.include_router(export.router, prefix="/export", tags=["Export"])
