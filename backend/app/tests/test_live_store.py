"""v2.3.0 live persistence: tracker + spooler + LiveCallStore, replayed from a PCAP."""
import os
import wave

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from app.capture.call_tracker import LiveCallTracker
from app.capture.live_store import LiveCallStore
from app.capture.packet_source import PcapReplaySource
from app.capture.rtp_spool import RTPSpooler
from app.core.rtp_analyzer import extract_sdp
from app.db.database import engine, Base, AsyncSessionLocal
from app.models.call import Call, CallStatus
from app.models.capture_file import CaptureFile
from app.models.rtp_stream import RTPStream
from app.models.sip_event import SIPEvent
from app.tests.test_audio import _build_call_with_rtp


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def recordings(tmp_path, monkeypatch):
    d = tmp_path / "recordings"
    monkeypatch.setenv("RECORDINGS_DIR", str(d))
    return d


async def _replay(pcap, tmp_path, store, *, final_only=False):
    """Drive the same loop the capture service will run; returns run id."""
    run_id = await store.start_run()
    tracker = LiveCallTracker()
    spool = RTPSpooler(str(tmp_path / "spool"))
    db_ids = {}

    async def handle(ev):
        cid = ev.session.call_id
        if ev.kind == "updated":
            spool.update_sdp(cid, extract_sdp(ev.session.packets))
            if not final_only:
                db_ids[cid] = await store.update(run_id, ev.session)
        else:
            data = spool.load(cid)
            db_ids[cid] = await store.finalize(run_id, ev.session, data)
            spool.close_call(cid)

    for cp in PcapReplaySource(str(pcap)):
        for ev in tracker.feed(cp):
            await handle(ev)
        cid = spool.feed(cp)
        if cid:
            tracker.note_media(cid, cp.timestamp)
    for ev in tracker.flush():
        await handle(ev)
    await store.end_run(run_id)
    return run_id


class TestLiveStore:
    @pytest.mark.asyncio
    async def test_answered_call_saved_with_events_metrics_and_audio(self, tmp_path, recordings):
        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        run_id = await _replay(pcap, tmp_path, LiveCallStore(AsyncSessionLocal))

        async with AsyncSessionLocal() as db:
            calls = (await db.execute(select(Call))).scalars().all()
            assert len(calls) == 1
            call = calls[0]
            assert call.status == CallStatus.ANSWERED
            assert call.source == "live"
            assert call.capture_file_id == run_id
            assert call.has_audio and call.audio_codec == "PCMU"
            assert (recordings / call.audio_path).exists()
            events = (await db.execute(select(func.count(SIPEvent.id)))).scalar()
            streams = (await db.execute(select(func.count(RTPStream.id)))).scalar()
            assert events >= 4
            assert streams >= 1
            run = await db.get(CaptureFile, run_id)
            assert run.kind == "live" and run.answered_count == 1 and run.calls_found == 1

        with wave.open(str(recordings / call.audio_path)) as w:
            assert w.getnchannels() == 2 and w.getnframes() >= 25 * 160

    @pytest.mark.asyncio
    async def test_finalize_is_idempotent_and_does_not_duplicate_children(self, tmp_path, recordings):
        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        store = LiveCallStore(AsyncSessionLocal)
        tracker = LiveCallTracker()
        run_id = await store.start_run()
        for cp in PcapReplaySource(str(pcap)):
            tracker.feed(cp)
        ev = tracker.flush()[0]
        await store.finalize(run_id, ev.session)
        await store.finalize(run_id, ev.session)
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(func.count(Call.id)))).scalar() == 1
            n = (await db.execute(select(func.count(SIPEvent.id)))).scalar()
            assert n == len(ev.session.packets)

    @pytest.mark.asyncio
    async def test_in_progress_update_then_final_status(self, tmp_path, recordings):
        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        store = LiveCallStore(AsyncSessionLocal)
        tracker = LiveCallTracker()
        run_id = await store.start_run()
        first = None
        for cp in PcapReplaySource(str(pcap)):
            for ev in tracker.feed(cp):
                if ev.kind == "updated" and first is None:
                    first = ev
                    await store.update(run_id, ev.session)
        async with AsyncSessionLocal() as db:
            call = (await db.execute(select(Call))).scalar_one()
            assert call.status == CallStatus.IN_PROGRESS
            assert (await db.execute(select(func.count(SIPEvent.id)))).scalar() == 0
        await store.finalize(run_id, tracker.flush()[0].session)
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Call))).scalar_one().status == CallStatus.ANSWERED

    @pytest.mark.asyncio
    async def test_recording_can_be_disabled(self, tmp_path, recordings):
        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        await _replay(pcap, tmp_path, LiveCallStore(AsyncSessionLocal, record_audio=False))
        async with AsyncSessionLocal() as db:
            call = (await db.execute(select(Call))).scalar_one()
            assert not call.has_audio
            assert (await db.execute(select(func.count(RTPStream.id)))).scalar() >= 1  # metrics still kept
        assert not recordings.exists() or not any(recordings.iterdir())

    @pytest.mark.asyncio
    async def test_recover_orphans_marks_stale_in_progress_unknown(self):
        async with AsyncSessionLocal() as db:
            db.add(Call(call_id="stale", status=CallStatus.IN_PROGRESS, source="live"))
            db.add(Call(call_id="upl", status=CallStatus.IN_PROGRESS, source="upload"))
            await db.commit()
        assert await LiveCallStore(AsyncSessionLocal).recover_orphans() == 1
        async with AsyncSessionLocal() as db:
            by = {c.call_id: c.status for c in (await db.execute(select(Call))).scalars()}
        assert by["stale"] == CallStatus.UNKNOWN and by["upl"] == CallStatus.IN_PROGRESS


class TestCaptureService:
    @pytest.mark.asyncio
    async def test_replay_through_service_matches_manual_pipeline(self, tmp_path, recordings):
        from app.capture.service import CaptureService, CaptureSettings

        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        svc = CaptureService(
            PcapReplaySource(str(pcap)),
            LiveCallStore(AsyncSessionLocal),
            CaptureSettings(spool_dir=str(tmp_path / "spool")),
            live=False,
        )
        await svc.run()
        async with AsyncSessionLocal() as db:
            call = (await db.execute(select(Call))).scalar_one()
            assert call.status == CallStatus.ANSWERED and call.source == "live" and call.has_audio
            run = await db.get(CaptureFile, svc.run_id)
            assert run.kind == "live" and run.calls_found == 1
        assert svc.stats["calls_finalized"] == 1 and svc.stats["errors"] == 0
        assert not any((tmp_path / "spool").iterdir())   # spool cleaned up

    @pytest.mark.asyncio
    async def test_store_failure_is_counted_and_does_not_stop_capture(self, tmp_path, recordings):
        from app.capture.service import CaptureService, CaptureSettings

        class Boom(LiveCallStore):
            async def finalize(self, *a, **k):
                raise RuntimeError("db down")

        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        svc = CaptureService(PcapReplaySource(str(pcap)), Boom(AsyncSessionLocal),
                             CaptureSettings(spool_dir=str(tmp_path / "spool")), live=False)
        await svc.run()
        assert svc.stats["errors"] == 1

    def test_settings_from_env(self, monkeypatch):
        from app.capture.service import CaptureSettings
        monkeypatch.setenv("CAPTURE_INTERFACE", "enp2s0")
        monkeypatch.setenv("LIVE_RECORDING_ENABLED", "false")
        monkeypatch.setenv("CAPTURE_SETTLE_SECONDS", "10")
        s = CaptureSettings.from_env()
        assert s.interface == "enp2s0" and s.record_audio is False and s.settle_seconds == 10.0


class TestNoEmptyRuns:
    @pytest.mark.asyncio
    async def test_idle_service_creates_no_capture_run(self, tmp_path, recordings):
        from app.capture.service import CaptureService, CaptureSettings

        empty = tmp_path / "empty.pcap"
        from scapy.all import wrpcap
        wrpcap(str(empty), [])
        svc = CaptureService(PcapReplaySource(str(empty)), LiveCallStore(AsyncSessionLocal),
                             CaptureSettings(spool_dir=str(tmp_path / "sp")), live=False)
        await svc.run()
        assert svc.run_id is None
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(func.count(CaptureFile.id)))).scalar() == 0

    @pytest.mark.asyncio
    async def test_purge_removes_empty_live_runs_but_keeps_uploads_and_used_runs(self, tmp_path, recordings):
        store = LiveCallStore(AsyncSessionLocal)
        for _ in range(3):
            await store.start_run()                      # empty leftovers from earlier restarts
        async with AsyncSessionLocal() as db:
            db.add(CaptureFile(filename="upload-no-calls.pcap", kind="upload"))
            await db.commit()
        assert await store.purge_empty_runs() == 3       # leftovers go
        assert await store.purge_empty_runs() == 0       # idempotent
        used = await _replay(_build_call_with_rtp(tmp_path / "a.pcap"), tmp_path, store)
        async with AsyncSessionLocal() as db:
            names = {f.filename for f in (await db.execute(select(CaptureFile))).scalars()}
        assert "upload-no-calls.pcap" in names and len(names) == 2
        assert any(n.startswith("Live capture") for n in names)
        assert used

    @pytest.mark.asyncio
    async def test_capture_file_list_hides_empty_live_runs(self, tmp_path, recordings):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        await LiveCallStore(AsyncSessionLocal).start_run()
        async with AsyncSessionLocal() as db:
            db.add(CaptureFile(filename="x.pcap", kind="upload"))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            names = [f["filename"] for f in (await c.get("/capture-files")).json()]
        assert names == ["x.pcap"]
