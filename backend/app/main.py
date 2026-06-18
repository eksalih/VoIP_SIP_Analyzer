from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.database import init_db
from app.api import calls, analytics, upload, health, replay, capture_files


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="VoIP SIP Analyzer",
    description="SIP packet capture analysis and call validation platform",
    version="1.1.1",
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
