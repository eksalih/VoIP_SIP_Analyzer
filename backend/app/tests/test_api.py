"""
Integration tests for REST API endpoints.
Uses httpx + in-memory SQLite database.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import engine, Base


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"


class TestCallsEndpoint:
    @pytest.mark.asyncio
    async def test_list_calls_empty(self, client):
        response = await client.get("/calls")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_call_not_found(self, client):
        response = await client.get("/calls/9999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_calls_filter_status(self, client):
        response = await client.get("/calls?status=ANSWERED")
        assert response.status_code == 200


class TestClearAllData:
    @pytest.mark.asyncio
    async def test_clear_all_requires_confirmation(self, client):
        """Without confirm=true, the endpoint must refuse to delete anything."""
        response = await client.delete("/calls/clear-all")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clear_all_with_confirmation_on_empty_db(self, client):
        response = await client.delete("/calls/clear-all?confirm=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["deleted"]["calls"] == 0

    @pytest.mark.asyncio
    async def test_clear_all_removes_uploaded_data(self, client, tmp_path):
        """Upload a synthetic PCAP, confirm it appears, then clear and confirm it's gone."""
        from scapy.all import IP, UDP, Raw, wrpcap
        import time

        sip_invite = (
            "INVITE sip:1002@127.0.0.1 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK776a\r\n"
            "From: <sip:1001@127.0.0.1>;tag=abc\r\n"
            "To: <sip:1002@127.0.0.1>\r\n"
            "Call-ID: clear-test-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        sip_200 = (
            "SIP/2.0 200 OK\r\n"
            "Call-ID: clear-test-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        sip_bye = (
            "BYE sip:1001@127.0.0.1 SIP/2.0\r\n"
            "Call-ID: clear-test-call@127.0.0.1\r\n"
            "CSeq: 2 BYE\r\n\r\n"
        )

        pkts = []
        for i, msg in enumerate([sip_invite, sip_200, sip_bye]):
            pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
            pkt.time = time.time() + i
            pkts.append(pkt)

        pcap_path = tmp_path / "clear_test.pcap"
        wrpcap(str(pcap_path), pkts)

        with open(pcap_path, "rb") as f:
            upload_resp = await client.post(
                "/upload-pcap",
                files={"file": ("clear_test.pcap", f, "application/octet-stream")},
            )
        assert upload_resp.status_code == 200

        list_resp = await client.get("/calls")
        assert len(list_resp.json()) >= 1

        clear_resp = await client.delete("/calls/clear-all?confirm=true")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["deleted"]["calls"] >= 1

        list_resp_after = await client.get("/calls")
        assert list_resp_after.json() == []


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_analytics_empty(self, client):
        response = await client.get("/analytics")
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0
        assert data["success_rate"] == 0.0
        assert data["answered"] == 0
