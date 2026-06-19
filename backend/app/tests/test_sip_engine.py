"""
Unit tests for SIP parser and call state machine.
Tests all call classification scenarios without requiring real PCAP files.
"""
import pytest
from datetime import datetime, timedelta

from app.core.sip_parser import parse_sip_message
from app.core.call_state_machine import (
    CallSession,
    classify_session,
    SIPPacket,
)


def _ts(offset_s: float = 0) -> datetime:
    return datetime(2024, 1, 15, 10, 0, 0) + timedelta(seconds=offset_s)


def _pkt(
    method=None,
    code=None,
    code_text=None,
    ts_offset=0,
    call_id="test-call-id",
    caller="1001",
    called="1002",
):
    p = SIPPacket()
    p.call_id = call_id
    p.timestamp = _ts(ts_offset)
    p.source_ip = "192.168.1.10"
    p.destination_ip = "192.168.1.20"
    if method:
        p.method = method.upper()
        p.is_request = True
        p.caller = caller
        p.called = called
    if code:
        p.response_code = code
        p.response_text = code_text or ""
        p.is_response = True
    return p


# ──────────────────────────────────────────────
# SIP Parser Tests
# ──────────────────────────────────────────────

class TestSIPParser:
    def test_parse_invite_request(self):
        raw = (
            "INVITE sip:1002@192.168.1.20 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 192.168.1.10:5060;branch=z9hG4bK776asdhds\r\n"
            "From: \"Alice\" <sip:1001@pbx.local>;tag=1928301774\r\n"
            "To: <sip:1002@pbx.local>\r\n"
            "Call-ID: abc123@192.168.1.10\r\n"
            "CSeq: 314159 INVITE\r\n"
            "User-Agent: Grandstream GXP2140\r\n"
        )
        result = parse_sip_message(raw)
        assert result["method"] == "INVITE"
        assert result["is_request"] is True
        assert result["call_id"] == "abc123@192.168.1.10"
        assert result["caller"] == "1001"
        assert result["called"] == "1002"
        assert result["display_name"] == "Alice"
        assert result["branch_id"] == "z9hG4bKk776asdhds" or result["branch_id"].startswith("z9hG4bK")
        assert result["user_agent"] == "Grandstream GXP2140"
        assert result["cseq_number"] == 314159
        assert result["cseq_method"] == "INVITE"

    def test_parse_200_ok(self):
        raw = (
            "SIP/2.0 200 OK\r\n"
            "Call-ID: abc123@192.168.1.10\r\n"
            "CSeq: 314159 INVITE\r\n"
        )
        result = parse_sip_message(raw)
        assert result["response_code"] == 200
        assert result["response_text"] == "OK"
        assert result["is_response"] is True

    def test_parse_486_busy(self):
        raw = (
            "SIP/2.0 486 Busy Here\r\n"
            "Call-ID: abc123@192.168.1.10\r\n"
        )
        result = parse_sip_message(raw)
        assert result["response_code"] == 486
        assert result["response_text"] == "Busy Here"

    def test_parse_603_decline(self):
        raw = (
            "SIP/2.0 603 Decline\r\n"
            "Call-ID: abc123@192.168.1.10\r\n"
        )
        result = parse_sip_message(raw)
        assert result["response_code"] == 603

    def test_parse_bye(self):
        raw = (
            "BYE sip:1001@192.168.1.10 SIP/2.0\r\n"
            "Call-ID: abc123@192.168.1.10\r\n"
        )
        result = parse_sip_message(raw)
        assert result["method"] == "BYE"

    def test_extract_sip_domain(self):
        raw = (
            "INVITE sip:1002@pbx.company.com SIP/2.0\r\n"
            "To: <sip:1002@pbx.company.com>\r\n"
            "Call-ID: xyz@host\r\n"
        )
        result = parse_sip_message(raw)
        assert result.get("sip_domain") == "pbx.company.com"


# ──────────────────────────────────────────────
# Call State Machine Tests
# ──────────────────────────────────────────────

class TestCallStateMachine:

    def _session_from_packets(self, pkts) -> CallSession:
        s = CallSession(call_id=pkts[0].call_id)
        s.packets = pkts
        return classify_session(s)

    def test_answered_call(self):
        """Full INVITE → 100 → 180 → 200 OK → ACK → BYE flow."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=100, ts_offset=0.1),
            _pkt(code=180, ts_offset=0.5),
            _pkt(code=200, ts_offset=6.0),
            _pkt("ACK", ts_offset=6.1),
            _pkt("BYE", ts_offset=120.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "ANSWERED"
        assert s.has_answer is True
        assert s.has_bye is True
        assert s.talk_duration is not None
        assert s.talk_duration == pytest.approx(114.0, abs=0.1)

    def test_missed_call(self):
        """INVITE → 180 Ringing → CANCEL (no 200 OK)."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=100, ts_offset=0.2),
            _pkt(code=180, ts_offset=1.0),
            _pkt("CANCEL", ts_offset=30.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "MISSED"
        assert s.has_ringing is True
        assert s.has_answer is False

    def test_rejected_486(self):
        """INVITE → 486 Busy Here = REJECTED (not MISSED)."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=100, ts_offset=0.1),
            _pkt(code=180, ts_offset=0.5),
            _pkt(code=486, code_text="Busy Here", ts_offset=2.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "REJECTED"
        assert s.rejection_code == 486
        assert s.rejection_reason == "Busy Here"

    def test_rejected_603(self):
        """INVITE → 603 Decline = REJECTED."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=100, ts_offset=0.1),
            _pkt(code=603, code_text="Decline", ts_offset=1.5),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "REJECTED"
        assert s.rejection_code == 603

    def test_rejected_600(self):
        """INVITE → 600 Busy Everywhere = REJECTED."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=600, code_text="Busy Everywhere", ts_offset=1.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "REJECTED"
        assert s.rejection_code == 600

    def test_rejected_is_not_missed(self):
        """Ensure 486/603 never produces MISSED status."""
        for code in (486, 603, 600):
            pkts = [
                _pkt("INVITE", ts_offset=0),
                _pkt(code=180, ts_offset=1.0),
                _pkt(code=code, ts_offset=3.0),
            ]
            s = self._session_from_packets(pkts)
            assert s.status == "REJECTED", f"Code {code} should produce REJECTED, got {s.status}"
            assert s.status != "MISSED"

    def test_cancelled_before_ringing(self):
        """INVITE → CANCEL without ringing = CANCELLED."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=100, ts_offset=0.1),
            _pkt("CANCEL", ts_offset=1.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "CANCELLED"

    def test_failed_call_no_response(self):
        """INVITE with no response = FAILED."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "FAILED"

    def test_failed_sip_error(self):
        """INVITE → 404 Not Found = FAILED."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=404, code_text="Not Found", ts_offset=1.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.status == "FAILED"

    def test_ring_duration_calculation(self):
        """Ring duration = time from 180 Ringing to 200 OK."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=180, ts_offset=2.0),
            _pkt(code=200, ts_offset=10.0),
            _pkt("BYE", ts_offset=70.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.ring_duration == pytest.approx(8.0, abs=0.1)
        assert s.talk_duration == pytest.approx(60.0, abs=0.1)
        assert s.total_duration == pytest.approx(70.0, abs=0.1)

    def test_metadata_extracted_from_invite(self):
        """Metadata (caller, called, etc.) comes from INVITE packet."""
        pkts = [
            _pkt("INVITE", ts_offset=0, caller="5551001", called="5551002"),
            _pkt(code=200, ts_offset=5.0),
            _pkt("BYE", ts_offset=60.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.caller == "5551001"
        assert s.called == "5551002"
        assert s.source_ip == "192.168.1.10"

    def test_session_183_treated_as_ringing(self):
        """183 Session Progress should trigger ringing state."""
        pkts = [
            _pkt("INVITE", ts_offset=0),
            _pkt(code=183, ts_offset=1.0),
            _pkt(code=200, ts_offset=8.0),
            _pkt("BYE", ts_offset=90.0),
        ]
        s = self._session_from_packets(pkts)
        assert s.has_ringing is True
        assert s.status == "ANSWERED"


# ──────────────────────────────────────────────
# Integration: Full pipeline test
# ──────────────────────────────────────────────

class TestPipeline:
    def test_multiple_calls_classified_correctly(self):
        from app.core.call_state_machine import group_packets_by_call, process_pcap_sessions

        # Build 3 calls: answered, missed, rejected
        answered_pkts = [
            _pkt("INVITE", ts_offset=0, call_id="call-a"),
            _pkt(code=180, ts_offset=1, call_id="call-a"),
            _pkt(code=200, ts_offset=5, call_id="call-a"),
            _pkt("BYE", ts_offset=60, call_id="call-a"),
        ]
        missed_pkts = [
            _pkt("INVITE", ts_offset=0, call_id="call-b"),
            _pkt(code=180, ts_offset=1, call_id="call-b"),
            _pkt("CANCEL", ts_offset=30, call_id="call-b"),
        ]
        rejected_pkts = [
            _pkt("INVITE", ts_offset=0, call_id="call-c"),
            _pkt(code=486, ts_offset=2, call_id="call-c"),
        ]

        all_pkts = answered_pkts + missed_pkts + rejected_pkts
        sessions = process_pcap_sessions(all_pkts)

        statuses = {s.call_id: s.status for s in sessions}
        assert statuses["call-a"] == "ANSWERED"
        assert statuses["call-b"] == "MISSED"
        assert statuses["call-c"] == "REJECTED"


class TestParserBackendSelection:
    """
    v1.2.0: Scapy is the default/primary parser (no external binary
    dependency). PyShark/tshark is opt-in via SIP_PARSER_BACKEND=pyshark.
    These tests confirm the selection logic and the safety fallback.
    """

    def test_default_backend_is_scapy(self, monkeypatch):
        monkeypatch.delenv("SIP_PARSER_BACKEND", raising=False)
        import importlib
        from app.core import sip_parser
        importlib.reload(sip_parser)
        assert sip_parser.PREFERRED_PARSER == "scapy"

    def test_env_var_can_request_pyshark(self, monkeypatch):
        monkeypatch.setenv("SIP_PARSER_BACKEND", "pyshark")
        import importlib
        from app.core import sip_parser
        importlib.reload(sip_parser)
        assert sip_parser.PREFERRED_PARSER == "pyshark"
        # Reset to default for subsequent tests in the suite
        monkeypatch.delenv("SIP_PARSER_BACKEND", raising=False)
        importlib.reload(sip_parser)

    def test_parse_pcap_file_works_without_tshark_installed(self, tmp_path):
        """
        The core promise of this release: parsing must succeed even when
        tshark is completely absent from the system (the default self-hosting
        scenario). We don't assert anything about tshark's presence/absence
        here -- we just confirm parse_pcap_file() produces correct results
        using whichever backend is actually available, which in a tshark-less
        environment must be Scapy.
        """
        from scapy.all import IP, UDP, Raw, wrpcap
        from app.core.sip_parser import parse_pcap_file
        import time

        sip_invite = (
            "INVITE sip:1002@127.0.0.1 SIP/2.0\r\n"
            "Call-ID: backend-test-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        sip_200 = (
            "SIP/2.0 200 OK\r\n"
            "Call-ID: backend-test-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )

        pkts = []
        for i, msg in enumerate([sip_invite, sip_200]):
            pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
            pkt.time = time.time() + i
            pkts.append(pkt)

        pcap_path = tmp_path / "backend_test.pcap"
        wrpcap(str(pcap_path), pkts)

        result = parse_pcap_file(str(pcap_path))
        assert len(result) == 2
        assert result[0].call_id == "backend-test-call@127.0.0.1"


class TestNotifyOverHttpFiltering:
    """
    Some PBXs (observed on a real Yeastar capture) emit 'NOTIFY * HTTP/1.1'
    traffic on the same port as SIP signaling -- this is NOT a SIP NOTIFY
    despite sharing the method name, and must never be parsed as one.
    """

    def test_notify_over_http_is_not_parsed_as_sip(self, tmp_path):
        from scapy.all import IP, UDP, Raw, wrpcap
        from app.core.sip_parser import parse_pcap_file
        import time

        real_invite = (
            "INVITE sip:1002@127.0.0.1 SIP/2.0\r\n"
            "Call-ID: real-call@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n\r\n"
        )
        # This mimics the noise pattern: method name NOTIFY but HTTP/1.1 version,
        # which is not a valid SIP request line and must be excluded.
        notify_http_noise = (
            "NOTIFY * HTTP/1.1\r\n"
            "Call-ID: should-not-appear@127.0.0.1\r\n"
            "Content-Length: 0\r\n\r\n"
        )

        pkts = []
        for i, msg in enumerate([real_invite, notify_http_noise]):
            pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
            pkt.time = time.time() + i
            pkts.append(pkt)

        pcap_path = tmp_path / "notify_noise_test.pcap"
        wrpcap(str(pcap_path), pkts)

        result = parse_pcap_file(str(pcap_path))
        call_ids = {p.call_id for p in result}

        assert "real-call@127.0.0.1" in call_ids
        assert "should-not-appear@127.0.0.1" not in call_ids
