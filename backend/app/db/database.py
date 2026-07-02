from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, inspect
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

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


# ── Lightweight auto-migration ──────────────────────────────────────────────
# SQLAlchemy's Base.metadata.create_all() only creates tables that don't exist
# yet -- it never alters an existing table to add new columns. Without this,
# upgrading the app to a version that adds a column (e.g. v2.0.0 -> v2.1.0
# added Call.vendor / Call.vendor_category) against an existing SQLite file
# from an older version causes every query to fail with
# "OperationalError: no such column: calls.vendor", which breaks uploads,
# the call list, and any endpoint that touches the affected table.
#
# This is not a full migration framework (no down-migrations, no version
# tracking) -- it's intentionally minimal: on every startup, compare each
# mapped table's expected columns against what's actually in the database,
# and ALTER TABLE ADD COLUMN for anything missing. SQLite supports adding
# nullable columns cheaply; this is safe to run on every startup and is a
# no-op once the schema is already current.
#
# Parametrized over (engine, base) rather than using the module-level
# `engine`/`Base` directly so it can be tested in isolation against a
# throwaway engine without needing to reload this module (which would
# create a second, disconnected Base that already-imported model classes
# aren't registered against).
def _get_existing_columns_sync(sync_conn, table_name: str) -> set[str]:
    inspector = inspect(sync_conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


async def _auto_migrate_missing_columns_for_engine(target_engine, declarative_base) -> None:
    async with target_engine.begin() as conn:
        for table in declarative_base.metadata.sorted_tables:
            existing_columns = await conn.run_sync(_get_existing_columns_sync, table.name)
            if not existing_columns:
                # Table doesn't exist yet -- create_all() handles it, nothing to migrate.
                continue

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(dialect=target_engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                logger.warning(
                    f"Auto-migration: adding missing column {table.name}.{column.name} "
                    f"(detected an older database schema from a previous version)"
                )
                await conn.execute(text(ddl))


async def init_db():
    from app.models import call, sip_event, test_run, capture_file, rtp_stream  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Run after create_all so brand-new installs (no existing tables) skip
    # migration entirely -- it only does anything for upgrades.
    await _auto_migrate_missing_columns_for_engine(engine, Base)


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
