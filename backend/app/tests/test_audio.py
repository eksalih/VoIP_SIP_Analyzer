"""
v2.2.0 tests: call-audio reconstruction (opt-in), the audio endpoint, file cleanup,
and the analytics orphan-stream guard.
"""
import os
import wave

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import engine, Base, AsyncSessionLocal
from app.models.rtp_stream import RTPStream


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


@pytest.fixture
def recordings(tmp_path, monkeypatch):
    """Enable audio saving into an isolated directory."""
    rec_dir = tmp_path / "recordings"
    monkeypatch.setenv("SAVE_CALL_AUDIO", "true")
    monkeypatch.setenv("RECORDINGS_DIR", str(rec_dir))
    return rec_dir


def _sdp(ip: str, port: int) -> str:
    return (
        "v=0\r\no=- 1 1 IN IP4 {ip}\r\ns=-\r\nc=IN IP4 {ip}\r\nt=0 0\r\n"
        "m=audio {port} RTP/AVP 0 101\r\na=rtpmap:0 PCMU/8000\r\na=ptime:20\r\n"
    ).format(ip=ip, port=port)


def _build_call_with_rtp(path, call_id="audio-test@host", payload_type=0, n_packets=25):
    """INVITE(SDP) -> 200 OK(SDP) -> BYE plus two-way RTP, written to a PCAP."""
    from scapy.all import IP, UDP, Raw, wrpcap

    t0 = 1_700_000_000.0
    pkts = []

    def sip(msg, i):
        p = IP(src="10.0.0.1", dst="10.0.0.2") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
        p.time = t0 + i * 0.01
        pkts.append(p)

    caller_sdp, callee_sdp = _sdp("10.0.0.1", 4000), _sdp("10.0.0.2", 6000)
    sip(
        f"INVITE sip:1002@10.0.0.2 SIP/2.0\r\nCall-ID: {call_id}\r\nCSeq: 1 INVITE\r\n"
        f"From: <sip:1001@10.0.0.1>;tag=a\r\nTo: <sip:1002@10.0.0.2>\r\n"
        f"Content-Type: application/sdp\r\n\r\n{caller_sdp}", 0)
    sip(
        f"SIP/2.0 200 OK\r\nCall-ID: {call_id}\r\nCSeq: 1 INVITE\r\n"
        f"Content-Type: application/sdp\r\n\r\n{callee_sdp}", 1)
    sip(f"ACK sip:1002@10.0.0.2 SIP/2.0\r\nCall-ID: {call_id}\r\nCSeq: 1 ACK\r\n\r\n", 2)

    def rtp(src, sport, dst, dport, seq, fill):
        header = bytes([0x80, payload_type]) + seq.to_bytes(2, "big") \
            + (seq * 160).to_bytes(4, "big") + (0x1234 + sport).to_bytes(4, "big")
        p = IP(src=src, dst=dst) / UDP(sport=sport, dport=dport) / Raw(load=header + bytes([fill]) * 160)
        p.time = t0 + 0.1 + seq * 0.02
        pkts.append(p)

    for seq in range(n_packets):
        rtp("10.0.0.1", 4000, "10.0.0.2", 6000, seq, 0x80)
        rtp("10.0.0.2", 6000, "10.0.0.1", 4000, seq, 0x00)

    sip(f"BYE sip:1001@10.0.0.1 SIP/2.0\r\nCall-ID: {call_id}\r\nCSeq: 2 BYE\r\n\r\n", 100)
    pkts.sort(key=lambda p: p.time)
    wrpcap(str(path), pkts)
    return path


async def _upload(client, path):
    with open(path, "rb") as f:
        resp = await client.post("/upload-pcap", files={"file": (os.path.basename(path), f, "application/octet-stream")})
    assert resp.status_code == 200
    return resp.json()


async def _first_call(client):
    calls = (await client.get("/calls")).json()
    assert calls, "expected at least one call"
    return calls[0]


class TestAudioReconstruction:
    @pytest.mark.asyncio
    async def test_audio_saved_and_served_when_enabled(self, client, tmp_path, recordings):
        await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap"))
        call = await _first_call(client)

        assert call["status"] == "ANSWERED"
        assert call["has_audio"] is True
        assert call["audio_codec"] == "PCMU"
        assert call["audio_duration"] > 0
        assert "audio_path" not in call  # server-side path never exposed

        resp = await client.get(f"/calls/{call['id']}/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"

        wav_file = tmp_path / "served.wav"
        wav_file.write_bytes(resp.content)
        with wave.open(str(wav_file)) as w:
            assert w.getnchannels() == 2      # caller left, callee right
            assert w.getframerate() == 8000
            assert w.getnframes() >= 25 * 160

    @pytest.mark.asyncio
    async def test_audio_not_saved_by_default(self, client, tmp_path, monkeypatch):
        monkeypatch.delenv("SAVE_CALL_AUDIO", raising=False)
        monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "recordings"))
        await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap"))
        call = await _first_call(client)

        assert call["has_audio"] is False
        assert (await client.get(f"/calls/{call['id']}/audio")).status_code == 404
        assert not (tmp_path / "recordings").exists()

    @pytest.mark.asyncio
    async def test_unsupported_codec_gives_no_audio_but_upload_succeeds(self, client, tmp_path, recordings):
        # PT 9 (G.722) is not decodable; the call must still be classified normally.
        await _upload(client, _build_call_with_rtp(tmp_path / "g722.pcap", payload_type=9))
        call = await _first_call(client)
        assert call["status"] == "ANSWERED"
        assert call["has_audio"] is False

    @pytest.mark.asyncio
    async def test_audio_404_for_unknown_call(self, client):
        assert (await client.get("/calls/9999/audio")).status_code == 404

    @pytest.mark.asyncio
    async def test_call_detail_includes_has_audio(self, client, tmp_path, recordings):
        """Detail endpoint rebuilds the schema from a dump — has_audio must survive."""
        await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap"))
        call = await _first_call(client)
        detail = (await client.get(f"/calls/{call['id']}")).json()
        assert detail["has_audio"] is True
        assert detail["audio_codec"] == "PCMU"


class TestAudioCleanup:
    @pytest.mark.asyncio
    async def test_delete_call_removes_wav(self, client, tmp_path, recordings):
        await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap"))
        call = await _first_call(client)
        assert len(list(recordings.glob("*.wav"))) == 1

        assert (await client.delete(f"/calls/{call['id']}")).status_code == 200
        assert list(recordings.glob("*.wav")) == []

    @pytest.mark.asyncio
    async def test_delete_capture_file_removes_wav(self, client, tmp_path, recordings):
        result = await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap"))
        assert len(list(recordings.glob("*.wav"))) == 1

        resp = await client.delete(f"/capture-files/{result['capture_file_id']}")
        assert resp.status_code == 200
        assert list(recordings.glob("*.wav")) == []

    @pytest.mark.asyncio
    async def test_clear_all_removes_wavs(self, client, tmp_path, recordings):
        await _upload(client, _build_call_with_rtp(tmp_path / "a.pcap", call_id="one@host"))
        await _upload(client, _build_call_with_rtp(tmp_path / "b.pcap", call_id="two@host"))
        assert len(list(recordings.glob("*.wav"))) == 2

        resp = await client.delete("/calls/clear-all?confirm=true")
        assert resp.status_code == 200
        assert resp.json()["deleted"]["audio_files"] == 2
        assert list(recordings.glob("*.wav")) == []


class TestAnalyticsOrphanGuard:
    @pytest.mark.asyncio
    async def test_orphaned_rtp_streams_are_not_counted(self, client):
        """RTP rows whose call no longer exists must not appear in analytics."""
        async with AsyncSessionLocal() as session:
            session.add(RTPStream(call_id=9999, packet_count=10, jitter_ms=5.0,
                                  packet_loss_pct=1.0, is_one_way=True))
            await session.commit()

        data = (await client.get("/analytics")).json()
        assert data["total_calls"] == 0
        assert data["rtp_streams_total"] == 0
        assert data["rtp_one_way_count"] == 0
        assert data["rtp_avg_jitter_ms"] is None
        assert data["rtp_avg_loss_pct"] is None
