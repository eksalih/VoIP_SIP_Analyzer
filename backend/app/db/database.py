from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path
import os

# Default SQLite path lives under ./data so a single `docker-compose.yml`
# volume mount (./data:/app/data) is enough to persist the database across
# container restarts/rebuilds. Without this, a self-hoster who restarts
# their container without realizing the DB file wasn't in a mounted volume
# would silently lose all call history.
_DEFAULT_DB_PATH = Path("data") / "voip_analyzer.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///./{_DEFAULT_DB_PATH}")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    from app.models import call, sip_event, test_run, capture_file, rtp_stream  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
