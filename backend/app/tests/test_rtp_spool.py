"""v2.3.0 tests: the live RTP spooler."""
import os
import struct
import wave

import pytest

from app.capture.call_tracker import LiveCallTracker
from app.capture.packet_source import CapturedPacket, PcapReplaySource
from app.capture.rtp_spool import RTPSpooler
from app.core.audio_reconstructor import reconstruct_audio
from app.core.call_state_machine import process_pcap_sessions
from app.core.rtp_analyzer import (
    CallSDP, SDPMediaDesc, analyze_rtp, compute_call_metrics, extract_sdp,
)
from app.core.sip_parser import parse_pcap_file
from app.tests.test_audio import _build_call_with_rtp

A_IP, A_PORT = "10.0.0.1", 4000
B_IP, B_PORT = "10.0.0.2", 6000


def rtp(src_ip, src_port, seq, t, pt=0, fill=0x80, ssrc=0xAAAA, payload_len=160, ext=False):
    first = 0x90 if ext else 0x80
    header = bytes([first, pt]) + struct.pack(">HII", seq & 0xFFFF, seq * 160, ssrc)
    if ext:  # one 32-bit extension word: profile id, length(1), 4 bytes
        header += struct.pack(">HH", 0xBEDE, 1) + b"\x00\x00\x00\x00"
    dst_ip, dst_port = (B_IP, B_PORT) if src_ip == A_IP else (A_IP, A_PORT)
    return CapturedPacket(t, src_ip, dst_ip, src_port, dst_port, "udp", header + bytes([fill]) * payload_len)


def sdp(a=True, b=True, ptime=20):
    return CallSDP(
        caller_sdp=SDPMediaDesc(A_IP, A_PORT, ptime_ms=ptime) if a else None,
        callee_sdp=SDPMediaDesc(B_IP, B_PORT, ptime_ms=ptime) if b else None,
    )


@pytest.fixture
def spooler(tmp_path):
    s = RTPSpooler(str(tmp_path / "spool"), flush_every=10)
    yield s
    s.close_all()


class TestMatchingAndSpooling:
    def test_both_directions_are_spooled_and_read_back(self, spooler):
        spooler.update_sdp("c1", sdp())
        for i in range(5):
            assert spooler.feed(rtp(A_IP, A_PORT, i, 100 + i * 0.02, fill=0x11)) == "c1"
            assert spooler.feed(rtp(B_IP, B_PORT, i, 100 + i * 0.02, fill=0x22, ssrc=0xBBBB)) == "c1"

        data = spooler.load("c1")
        assert data.total_packets == 10 and len(data.a2b) == 5 and len(data.b2a) == 5
        assert all(p.payload == bytes([0x11]) * 160 for p in data.a2b)
        assert all(p.payload == bytes([0x22]) * 160 for p in data.b2a)
        assert data.a2b[0].source_ip == A_IP and data.a2b[0].destination_ip == B_IP
        assert data.b2a[0].source_port == B_PORT and data.b2a[0].destination_port == A_PORT
        assert [p.sequence for p in data.a2b] == [0, 1, 2, 3, 4]

    def test_packets_from_unregistered_sources_are_ignored(self, spooler):
        spooler.update_sdp("c1", sdp())
        assert spooler.feed(rtp("9.9.9.9", 5000, 1, 100.0)) is None
        assert spooler.feed(rtp(A_IP, 4002, 1, 100.0)) is None          # right IP, wrong port
        assert spooler.packet_count("c1") == 0

    def test_non_udp_and_non_rtp_payloads_are_ignored(self, spooler):
        spooler.update_sdp("c1", sdp())
        tcp = CapturedPacket(1.0, A_IP, B_IP, A_PORT, B_PORT, "tcp", b"\x80\x00" + b"\x00" * 170)
        junk = CapturedPacket(1.0, A_IP, B_IP, A_PORT, B_PORT, "udp", b"not rtp at all")
        short = CapturedPacket(1.0, A_IP, B_IP, A_PORT, B_PORT, "udp", b"\x80\x00")
        assert [spooler.feed(p) for p in (tcp, junk, short)] == [None, None, None]

    def test_dtmf_and_rtcp_are_skipped(self, spooler):
        spooler.update_sdp("c1", sdp())
        assert spooler.feed(rtp(A_IP, A_PORT, 1, 100.0, pt=101)) is None
        assert spooler.feed(rtp(A_IP, A_PORT, 2, 100.0, pt=72)) is None   # RTCP SR (200 & 0x7F)
        assert spooler.feed(rtp(A_IP, A_PORT, 3, 100.0, pt=0)) == "c1"

    def test_mirror_duplicates_are_dropped_but_distinct_packets_kept(self, spooler):
        spooler.update_sdp("c1", sdp())
        p = rtp(A_IP, A_PORT, 7, 100.0)
        assert spooler.feed(p) == "c1"
        assert spooler.feed(p) is None                      # same ssrc+seq again
        assert spooler.feed(rtp(A_IP, A_PORT, 8, 100.02)) == "c1"
        assert spooler.packet_count("c1") == 2

    def test_rtp_extension_header_is_skipped(self, spooler):
        spooler.update_sdp("c1", sdp())
        spooler.feed(rtp(A_IP, A_PORT, 1, 100.0, ext=True, fill=0x55))
        pkt = spooler.load("c1").a2b[0]
        assert pkt.payload == bytes([0x55]) * 160

    def test_concurrent_calls_do_not_mix(self, spooler):
        spooler.update_sdp("c1", sdp())
        other = CallSDP(
            caller_sdp=SDPMediaDesc("10.0.1.1", 4100), callee_sdp=SDPMediaDesc("10.0.1.2", 6100)
        )
        spooler.update_sdp("c2", other)
        spooler.feed(rtp(A_IP, A_PORT, 1, 100.0))
        spooler.feed(CapturedPacket(100.0, "10.0.1.1", "10.0.1.2", 4100, 6100, "udp",
                                    rtp(A_IP, A_PORT, 1, 100.0).payload))
        assert spooler.packet_count("c1") == 1 and spooler.packet_count("c2") == 1


class TestSdpHandling:
    def test_media_before_callee_sdp_is_missed_then_picked_up(self, spooler):
        spooler.update_sdp("c1", sdp(b=False))               # only the INVITE's SDP so far
        assert spooler.feed(rtp(B_IP, B_PORT, 1, 100.0)) is None
        spooler.update_sdp("c1", sdp())                      # 200 OK arrives
        assert spooler.feed(rtp(B_IP, B_PORT, 2, 100.02)) == "c1"
        assert spooler.feed(rtp(A_IP, A_PORT, 1, 100.0)) == "c1"

    def test_reinvite_moving_media_switches_endpoints(self, spooler):
        spooler.update_sdp("c1", sdp())
        moved = CallSDP(caller_sdp=SDPMediaDesc(A_IP, 4010), callee_sdp=SDPMediaDesc(B_IP, B_PORT))
        spooler.update_sdp("c1", moved)
        assert spooler.feed(rtp(A_IP, A_PORT, 1, 100.0)) is None           # old port no longer ours
        assert spooler.feed(rtp(A_IP, 4010, 1, 100.0)) == "c1"

    def test_sdp_without_media_registers_nothing(self, spooler):
        spooler.update_sdp("c1", CallSDP())
        assert not spooler.has_call("c1")

    def test_ptime_is_remembered(self, spooler):
        spooler.update_sdp("c1", sdp(ptime=30))
        spooler.feed(rtp(A_IP, A_PORT, 1, 100.0))
        assert spooler.load("c1").ptime_ms == 30


class TestLifecycleAndRobustness:
    def test_last_media_time_tracks_the_newest_packet(self, spooler):
        spooler.update_sdp("c1", sdp())
        assert spooler.last_media_time("c1") is None
        spooler.feed(rtp(A_IP, A_PORT, 1, 100.0))
        spooler.feed(rtp(B_IP, B_PORT, 1, 100.5, ssrc=0xBBBB))
        assert spooler.last_media_time("c1") == 100.5

    def test_close_call_removes_file_and_frees_endpoints(self, spooler):
        spooler.update_sdp("c1", sdp())
        spooler.feed(rtp(A_IP, A_PORT, 1, 100.0))
        path = spooler._calls["c1"].path
        assert os.path.exists(path)
        spooler.close_call("c1")
        assert not os.path.exists(path)
        assert spooler.feed(rtp(A_IP, A_PORT, 2, 100.02)) is None
        assert spooler.load("c1") is None

    def test_endpoint_can_be_reused_by_a_later_call(self, spooler):
        spooler.update_sdp("c1", sdp())
        spooler.close_call("c1")
        spooler.update_sdp("c2", sdp())
        assert spooler.feed(rtp(A_IP, A_PORT, 1, 200.0)) == "c2"

    def test_data_reaches_disk_without_waiting_for_load(self, spooler):
        spooler.update_sdp("c1", sdp())
        for i in range(10):                                   # flush_every=10
            spooler.feed(rtp(A_IP, A_PORT, i, 100 + i * 0.02))
        assert os.path.getsize(spooler._calls["c1"].path) > 0

    def test_torn_final_record_is_tolerated(self, spooler):
        spooler.update_sdp("c1", sdp())
        for i in range(3):
            spooler.feed(rtp(A_IP, A_PORT, i, 100 + i * 0.02))
        spooler._calls["c1"].handle.flush()
        with open(spooler._calls["c1"].path, "ab") as f:
            f.write(b"\x00\x01\x02")                          # crash mid-record
        assert len(spooler.load("c1").a2b) == 3

    def test_loss_and_one_way_are_visible_in_metrics(self, spooler):
        spooler.update_sdp("c1", sdp())
        for seq in (0, 1, 2, 5, 6, 7):                        # 3 and 4 never arrive
            spooler.feed(rtp(A_IP, A_PORT, seq, 100 + seq * 0.02))
        data = spooler.load("c1")
        metrics = compute_call_metrics(data.a2b, data.b2a, data.ptime_ms)
        assert len(metrics) == 1 and metrics[0].is_one_way
        assert metrics[0].packet_loss_count == 2


class TestEquivalenceWithUploadPipeline:
    """Tracker + spooler over a replayed capture must give the same media results
    as processing the same capture through the upload pipeline."""

    def _live(self, path, spool_dir):
        tracker, spooler = LiveCallTracker(), RTPSpooler(str(spool_dir))
        for cp in PcapReplaySource(str(path)):
            for ev in tracker.feed(cp):
                if ev.kind == "updated":
                    spooler.update_sdp(ev.session.call_id, extract_sdp(ev.session.packets))
            spooler.feed(cp)
        return spooler

    def test_metrics_match_offline(self, tmp_path):
        pcap = _build_call_with_rtp(tmp_path / "call.pcap", call_id="eq@host", n_packets=40)
        sessions = process_pcap_sessions(parse_pcap_file(str(pcap)))
        offline = analyze_rtp(str(pcap), sessions, {s.call_id: s.packets for s in sessions})["eq@host"]

        spooler = self._live(pcap, tmp_path / "spool")
        data = spooler.load("eq@host")
        live = compute_call_metrics(data.a2b, data.b2a, data.ptime_ms)
        spooler.close_all()

        assert len(live) == len(offline) == 2
        for lv, off in zip(live, offline):
            assert (lv.packet_count, lv.packet_loss_count, lv.codec, lv.is_one_way) == \
                   (off.packet_count, off.packet_loss_count, off.codec, off.is_one_way)
            assert lv.jitter_ms == pytest.approx(off.jitter_ms)
            assert lv.duration_seconds == pytest.approx(off.duration_seconds)

    def test_reconstructed_wav_is_identical_to_offline(self, tmp_path):
        from app.core.rtp_analyzer import extract_rtp_packets, correlate

        pcap = _build_call_with_rtp(tmp_path / "call.pcap", call_id="eq@host", n_packets=40)
        sessions = process_pcap_sessions(parse_pcap_file(str(pcap)))
        sdp_info = extract_sdp(sessions[0].packets)
        a2b, b2a = correlate(extract_rtp_packets(str(pcap), keep_payload=True), sdp_info)
        reconstruct_audio(a2b, b2a, str(tmp_path / "offline.wav"))

        spooler = self._live(pcap, tmp_path / "spool")
        data = spooler.load("eq@host")
        result = reconstruct_audio(data.a2b, data.b2a, str(tmp_path / "live.wav"))
        spooler.close_all()

        assert result.channels == 2 and result.codec == "PCMU"
        with wave.open(str(tmp_path / "offline.wav")) as w1, wave.open(str(tmp_path / "live.wav")) as w2:
            assert w1.getparams() == w2.getparams()
            assert w1.readframes(w1.getnframes()) == w2.readframes(w2.getnframes())
