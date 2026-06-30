"""
Regression tests for the lightweight auto-migration in app/db/database.py.

Context: upgrading from v2.0.0 to v2.1.0 added Call.vendor and
Call.vendor_category columns. SQLAlchemy's Base.metadata.create_all() only
creates missing TABLES, never adds missing COLUMNS to existing tables. A
user who upgraded the app code without also migrating their existing SQLite
file hit "OperationalError: no such column: calls.vendor" on every upload,
breaking the call list, analytics, and replay test simultaneously.

These tests simulate that exact scenario: a database created with an OLDER
table schema (missing the newer columns), then run the migration against it
directly and confirm the missing columns are added.

Implementation note: these tests call the engine-parametrized internals
directly rather than monkeypatching DATABASE_URL + importlib.reload(), since
reloading app.db.database creates a NEW SQLAlchemy declarative Base while
already-imported model modules (app.models.call, etc.) remain registered
against the OLD Base -- this causes flaky "NoSuchTableError" failures
depending on test execution order. Testing the engine-level logic directly
avoids that fragility entirely.
"""
import pytest
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.database import Base, _auto_migrate_missing_columns_for_engine
import app.models.call, app.models.sip_event, app.models.test_run  # noqa: F401
import app.models.capture_file, app.models.rtp_stream  # noqa: F401


OLD_SCHEMA_DDL = [
    """CREATE TABLE capture_files (
        id INTEGER PRIMARY KEY, filename VARCHAR NOT NULL, file_size_bytes INTEGER,
        packets_parsed INTEGER, calls_found INTEGER, answered_count INTEGER,
        missed_count INTEGER, rejected_count INTEGER, failed_count INTEGER,
        cancelled_count INTEGER, processing_time_seconds FLOAT, uploaded_at DATETIME,
        label VARCHAR
    )""",
    # Deliberately missing `vendor` and `vendor_category` -- this is the
    # pre-v2.1.0 shape of the calls table.
    """CREATE TABLE calls (
        id INTEGER PRIMARY KEY, capture_file_id INTEGER, call_id VARCHAR NOT NULL,
        caller VARCHAR, called VARCHAR, display_name VARCHAR, source_ip VARCHAR,
        destination_ip VARCHAR, user_agent VARCHAR, sip_domain VARCHAR, branch_id VARCHAR,
        start_time DATETIME, ring_time DATETIME, answer_time DATETIME, end_time DATETIME,
        ring_duration FLOAT, talk_duration FLOAT, total_duration FLOAT,
        status VARCHAR NOT NULL, sip_result_code INTEGER, rejection_reason VARCHAR,
        created_at DATETIME
    )""",
    """CREATE TABLE sip_events (
        id INTEGER PRIMARY KEY, call_id INTEGER, timestamp DATETIME, sip_method VARCHAR,
        sip_response_code INTEGER, sip_response_text VARCHAR, source_ip VARCHAR,
        destination_ip VARCHAR, raw_message TEXT, sequence_number INTEGER
    )""",
    """CREATE TABLE test_runs (
        id INTEGER PRIMARY KEY, call_id INTEGER, capture_file_name VARCHAR,
        expected_status VARCHAR, detected_status VARCHAR, result VARCHAR,
        execution_time FLOAT, notes VARCHAR, passed BOOLEAN, created_at DATETIME
    )""",
    # rtp_streams intentionally omitted entirely -- create_all() already
    # handles brand-new tables correctly; this matches a real pre-v2.0.0 DB.
]


async def _make_old_schema_engine(tmp_path, name="old_schema.db"):
    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        for ddl in OLD_SCHEMA_DDL:
            await conn.execute(text(ddl))
    return engine


def _get_columns(sync_conn, table_name: str) -> set[str]:
    inspector = sa_inspect(sync_conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


class TestAutoMigration:
    @pytest.mark.asyncio
    async def test_missing_columns_are_added(self, tmp_path):
        """
        Simulates upgrading app code (with vendor/vendor_category columns)
        against an existing database that predates those columns.
        After running the migration, both columns must exist.
        """
        engine = await _make_old_schema_engine(tmp_path)

        async with engine.begin() as conn:
            before = await conn.run_sync(_get_columns, "calls")
        assert "vendor" not in before
        assert "vendor_category" not in before

        await _auto_migrate_missing_columns_for_engine(engine, Base)

        async with engine.begin() as conn:
            after = await conn.run_sync(_get_columns, "calls")
        assert "vendor" in after
        assert "vendor_category" in after

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_upload_succeeds_after_migrating_old_database(self, tmp_path):
        """
        End-to-end regression test for the exact bug report: uploading a PCAP
        against a database that predates the vendor columns must succeed,
        not fail with 'no such column: calls.vendor'.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await _make_old_schema_engine(tmp_path, "upload_test.db")
        # create_all() adds rtp_streams (missing entirely in the old schema);
        # the auto-migration adds the missing columns to `calls`.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _auto_migrate_missing_columns_for_engine(engine, Base)

        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        from app.services.pcap_service import process_pcap
        from scapy.all import IP, UDP, Raw, wrpcap
        import time

        sip_invite = (
            "INVITE sip:1002@127.0.0.1 SIP/2.0\r\n"
            "Call-ID: migration-test-call@127.0.0.1\r\n"
            "User-Agent: Yeastar S20-65.16.0.183\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        sip_200 = (
            "SIP/2.0 200 OK\r\n"
            "Call-ID: migration-test-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        pkts = []
        for i, msg in enumerate([sip_invite, sip_200]):
            pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
            pkt.time = time.time() + i
            pkts.append(pkt)
        pcap_path = tmp_path / "migration_test.pcap"
        wrpcap(str(pcap_path), pkts)

        async with SessionLocal() as session:
            result = await process_pcap(
                file_path=str(pcap_path),
                filename="migration_test.pcap",
                db=session,
            )
            await session.commit()

        assert result["status"] == "ok", f"Upload failed against migrated old DB: {result}"
        assert result["calls_processed"] == 1

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_migration_is_idempotent(self, tmp_path):
        """Running the migration twice in a row must not error (e.g. trying
        to add a column that already exists)."""
        engine = await _make_old_schema_engine(tmp_path, "idempotent.db")

        await _auto_migrate_missing_columns_for_engine(engine, Base)
        await _auto_migrate_missing_columns_for_engine(engine, Base)  # must not raise

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_brand_new_database_is_unaffected(self, tmp_path):
        """A fresh install (tables created fresh via create_all(), already
        matching the current model) must be a complete no-op for the
        migration step -- nothing to add, nothing should break."""
        db_path = tmp_path / "brand_new.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await _auto_migrate_missing_columns_for_engine(engine, Base)  # must not raise

        async with engine.begin() as conn:
            cols = await conn.run_sync(_get_columns, "calls")
        assert "vendor" in cols
        assert "vendor_category" in cols

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_empty_database_with_no_tables_is_unaffected(self, tmp_path):
        """A completely empty SQLite file (no tables at all) must not crash
        the migration -- create_all() is responsible for creating tables;
        the migration step should just skip tables that don't exist yet."""
        db_path = tmp_path / "completely_empty.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

        await _auto_migrate_missing_columns_for_engine(engine, Base)  # must not raise

        await engine.dispose()
