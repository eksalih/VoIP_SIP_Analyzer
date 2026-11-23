"""v2.3.0 recording retention: age limit, size cap, record kept, safe defaults."""
import os
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.database import engine, Base, AsyncSessionLocal
from app.models.call import Call, CallStatus
from app.services.retention import run_retention, retention_settings

NOW = datetime(2026, 11, 23, 12, 0, 0)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def rec_dir(tmp_path, monkeypatch):
    d = tmp_path / "rec"
    d.mkdir()
    monkeypatch.setenv("RECORDINGS_DIR", str(d))
    return d


async def _add(rec_dir, name, age_days, size=1000, status=CallStatus.ANSWERED):
    (rec_dir / name).write_bytes(b"x" * size)
    async with AsyncSessionLocal() as db:
        db.add(Call(call_id=name, status=status, start_time=NOW - timedelta(days=age_days),
                    audio_path=name, audio_codec="PCMU", audio_duration=5.0))
        await db.commit()


async def _calls():
    async with AsyncSessionLocal() as db:
        return {c.call_id: c for c in (await db.execute(select(Call))).scalars()}


class TestRetention:
    @pytest.mark.asyncio
    async def test_old_recordings_removed_but_call_record_kept(self, rec_dir):
        await _add(rec_dir, "old.wav", 200)
        await _add(rec_dir, "new.wav", 10)
        r = await run_retention(AsyncSessionLocal, days=180, max_gb=0, now=NOW)
        assert (r.expired, r.over_limit, r.freed_bytes) == (1, 0, 1000)
        calls = await _calls()
        assert set(calls) == {"old.wav", "new.wav"}            # records stay
        assert calls["old.wav"].audio_path is None and not calls["old.wav"].has_audio
        assert not (rec_dir / "old.wav").exists()
        assert calls["new.wav"].has_audio and (rec_dir / "new.wav").exists()

    @pytest.mark.asyncio
    async def test_zero_days_keeps_everything(self, rec_dir):
        await _add(rec_dir, "ancient.wav", 5000)
        r = await run_retention(AsyncSessionLocal, days=0, max_gb=0, now=NOW)
        assert r.removed == 0 and (rec_dir / "ancient.wav").exists()

    @pytest.mark.asyncio
    async def test_size_cap_deletes_oldest_first(self, rec_dir):
        mb = 1024 * 1024
        await _add(rec_dir, "a.wav", 30, size=mb)
        await _add(rec_dir, "b.wav", 20, size=mb)
        await _add(rec_dir, "c.wav", 10, size=mb)
        # cap = 2.5 MB -> only the oldest has to go
        r = await run_retention(AsyncSessionLocal, days=0, max_gb=2.5 / 1024, now=NOW)
        assert r.over_limit == 1
        calls = await _calls()
        assert not calls["a.wav"].has_audio
        assert calls["b.wav"].has_audio and calls["c.wav"].has_audio

    @pytest.mark.asyncio
    async def test_in_progress_calls_are_never_touched(self, rec_dir):
        await _add(rec_dir, "live.wav", 400, status=CallStatus.IN_PROGRESS)
        r = await run_retention(AsyncSessionLocal, days=180, max_gb=0, now=NOW)
        assert r.removed == 0 and (rec_dir / "live.wav").exists()

    @pytest.mark.asyncio
    async def test_missing_file_is_handled(self, rec_dir):
        await _add(rec_dir, "gone.wav", 300)
        os.unlink(rec_dir / "gone.wav")
        r = await run_retention(AsyncSessionLocal, days=180, max_gb=0, now=NOW)
        assert r.expired == 1 and r.freed_bytes == 0
        assert not (await _calls())["gone.wav"].has_audio

    def test_settings_defaults_and_bad_values(self, monkeypatch):
        monkeypatch.delenv("RECORDINGS_RETENTION_DAYS", raising=False)
        monkeypatch.delenv("RECORDINGS_MAX_GB", raising=False)
        assert retention_settings() == (180, 0.0)
        monkeypatch.setenv("RECORDINGS_RETENTION_DAYS", "abc")
        monkeypatch.setenv("RECORDINGS_MAX_GB", "250")
        assert retention_settings() == (180, 250.0)
