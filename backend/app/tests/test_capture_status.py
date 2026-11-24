"""v2.3.0 capture status hand-off between the capture container and the backend."""
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.capture.live_store import LiveCallStore
from app.capture.packet_source import PcapReplaySource
from app.capture.service import CaptureService, CaptureSettings
from app.capture.status import read_status, write_status
from app.db.database import engine, Base, AsyncSessionLocal
from app.main import app
from app.tests.test_audio import _build_call_with_rtp


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_STATUS_FILE", str(tmp_path / "status.json"))
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "rec"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class TestStatusFile:
    def test_missing_file_is_not_configured(self):
        assert read_status() == {"state": "not_configured"}

    def test_running_then_stale_without_heartbeat(self):
        write_status({"running": True, "interface": "eth1", "packets": 5})
        fresh = read_status()
        assert fresh["state"] == "running" and fresh["interface"] == "eth1"
        later = read_status(now=fresh["updated_at"] + 60)
        assert later["state"] == "stale"

    def test_clean_stop_is_stopped_not_stale(self):
        write_status({"running": False})
        assert read_status(now=read_status()["updated_at"] + 3600)["state"] == "stopped"

    def test_corrupt_file_reports_stale(self, tmp_path):
        (tmp_path / "status.json").write_text("{not json")
        assert read_status()["state"] == "stale"

    def test_write_is_atomic_and_leaves_no_temp_file(self, tmp_path):
        write_status({"running": True})
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith("status")] == ["status.json"]


class TestServiceReportsStatus:
    @pytest.mark.asyncio
    async def test_service_publishes_running_then_stopped(self, tmp_path):
        pcap = _build_call_with_rtp(tmp_path / "a.pcap")
        svc = CaptureService(PcapReplaySource(str(pcap)), LiveCallStore(AsyncSessionLocal),
                             CaptureSettings(interface="enp2s0", spool_dir=str(tmp_path / "sp")), live=False)
        await svc.run()
        data = json.loads((tmp_path / "status.json").read_text())
        assert data["running"] is False and data["interface"] == "enp2s0"
        assert data["packets"] > 0 and data["calls_finalized"] == 1 and data["open_calls"] == 0


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_returns_status(self):
        write_status({"running": True, "interface": "eth1"})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            body = (await c.get("/capture/status")).json()   # default test user is admin
        assert body["state"] == "running" and body["interface"] == "eth1"
