"""v2.3.0 tests: packet sources for the live capture service."""
import socket
import threading
import time
from pathlib import Path

import pytest
from scapy.all import Ether, Dot1Q, IP, UDP, TCP, ICMP, Raw, wrpcap

from app.capture.packet_source import (
    CapturedPacket, PcapReplaySource, LiveInterfaceSource, to_captured_packet,
)

FIXTURES = Path(__file__).parent / "fixtures" / "yeastar"


def _udp(payload=b"hello", t=1000.0, src="10.0.0.1", dst="10.0.0.2", sport=5060, dport=5060):
    p = Ether() / IP(src=src, dst=dst) / UDP(sport=sport, dport=dport) / Raw(load=payload)
    p.time = t
    return p


class TestToCapturedPacket:
    def test_udp_fields(self):
        cp = to_captured_packet(_udp(b"abc", t=1234.5))
        assert cp == CapturedPacket(1234.5, "10.0.0.1", "10.0.0.2", 5060, 5060, "udp", b"abc")

    def test_tcp_payload_is_yielded_as_tcp(self):
        p = Ether() / IP(src="1.1.1.1", dst="2.2.2.2") / TCP(sport=40000, dport=5060) / Raw(load=b"INVITE")
        p.time = 5.0
        cp = to_captured_packet(p)
        assert cp.protocol == "tcp" and cp.payload == b"INVITE" and cp.dst_port == 5060

    def test_vlan_tagged_packet_is_transparent(self):
        p = Ether() / Dot1Q(vlan=100) / IP(src="10.0.0.1", dst="10.0.0.2") / UDP(sport=1, dport=2) / Raw(load=b"x")
        p.time = 1.0
        cp = to_captured_packet(p)
        assert cp is not None and cp.payload == b"x" and cp.src_ip == "10.0.0.1"

    def test_non_udp_tcp_and_empty_payloads_are_skipped(self):
        assert to_captured_packet(Ether() / IP() / ICMP()) is None
        assert to_captured_packet(Ether() / IP() / UDP(sport=1, dport=2)) is None          # empty UDP
        assert to_captured_packet(Ether() / IP() / TCP(sport=1, dport=2)) is None          # TCP ACK, no data
        assert to_captured_packet(Ether()) is None


class TestPcapReplaySource:
    def test_replays_packets_in_order(self, tmp_path):
        path = tmp_path / "a.pcap"
        wrpcap(str(path), [_udp(b"one", 1.0), _udp(b"two", 2.0), Ether() / IP() / ICMP(), _udp(b"three", 3.0)])
        payloads = [cp.payload for cp in PcapReplaySource(str(path))]
        assert payloads == [b"one", b"two", b"three"]

    def test_reads_pcapng_fixture(self):
        packets = list(PcapReplaySource(str(FIXTURES / "answered_clean.pcapng")))
        assert len(packets) > 0
        assert all(isinstance(p, CapturedPacket) for p in packets)
        assert any(b"INVITE" in p.payload for p in packets)

    def test_stop_ends_iteration_early(self, tmp_path):
        path = tmp_path / "a.pcap"
        wrpcap(str(path), [_udp(b"%d" % i, float(i)) for i in range(50)])
        source = PcapReplaySource(str(path))
        seen = []
        for cp in source:
            seen.append(cp)
            if len(seen) == 3:
                source.stop()
        assert len(seen) == 3

    def test_pacing_follows_capture_timing(self, tmp_path):
        path = tmp_path / "a.pcap"
        wrpcap(str(path), [_udp(b"a", 100.0), _udp(b"b", 100.3)])
        start = time.monotonic()
        list(PcapReplaySource(str(path), speed=1.0))
        assert time.monotonic() - start >= 0.25

        start = time.monotonic()
        list(PcapReplaySource(str(path), speed=None))
        assert time.monotonic() - start < 0.2

    def test_stop_interrupts_a_long_pacing_gap(self, tmp_path):
        path = tmp_path / "a.pcap"
        wrpcap(str(path), [_udp(b"a", 100.0), _udp(b"b", 160.0)])   # 60 s gap
        source = PcapReplaySource(str(path), speed=1.0)
        threading.Timer(0.2, source.stop).start()
        start = time.monotonic()
        got = list(source)
        assert time.monotonic() - start < 5
        assert [c.payload for c in got] == [b"a"]


def _can_sniff_loopback() -> bool:
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        s.close()
        return True
    except (AttributeError, PermissionError, OSError):
        return False


@pytest.mark.skipif(not _can_sniff_loopback(), reason="raw sockets not permitted here")
class TestLiveInterfaceSource:
    def test_captures_udp_sent_over_loopback(self):
        source = LiveInterfaceSource("lo", bpf_filter="udp port 45061")
        got = []

        def consume():
            for cp in source:
                got.append(cp)

        t = threading.Thread(target=consume, daemon=True)
        t.start()
        time.sleep(1.0)  # let the sniffer attach

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(5):
            sock.sendto(b"live-%d" % i, ("127.0.0.1", 45061))
        sock.close()

        deadline = time.time() + 5
        while len(got) < 5 and time.time() < deadline:
            time.sleep(0.1)
        source.stop()
        t.join(timeout=5)

        payloads = {cp.payload for cp in got}
        assert {b"live-%d" % i for i in range(5)} <= payloads
        assert source.dropped == 0

    def test_full_queue_drops_and_counts_instead_of_growing(self):
        source = LiveInterfaceSource("lo", queue_size=2)
        pkt = _udp(b"x")
        for _ in range(5):
            source._on_packet(pkt)
        assert source.captured == 2
        assert source.dropped == 3
