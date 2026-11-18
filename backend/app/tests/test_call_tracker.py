"""v2.3.0 tests: the live call tracker."""
from pathlib import Path

import pytest

from app.capture.call_tracker import LiveCallTracker, TrackerEvent
from app.capture.packet_source import CapturedPacket, PcapReplaySource
from app.core.call_state_machine import process_pcap_sessions
from app.core.sip_parser import parse_pcap_file

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "yeastar").glob("*.pcapng"))

CALLER, CALLEE = "10.0.0.1", "10.0.0.2"


def sip(first_line, call_id, cseq, t, src=CALLER, dst=CALLEE, from_="1001", to="1002", extra=""):
    msg = (
        f"{first_line}\r\nCall-ID: {call_id}\r\nCSeq: {cseq}\r\n"
        f"From: <sip:{from_}@{CALLER}>;tag=a\r\nTo: <sip:{to}@{CALLEE}>\r\n"
        f"Via: SIP/2.0/UDP {CALLER}:5060;branch=z9hG4bKabc\r\n{extra}\r\n"
    )
    return CapturedPacket(t, src, dst, 5060, 5060, "udp", msg.encode())


def invite(cid, t=100.0):
    return sip(f"INVITE sip:1002@{CALLEE} SIP/2.0", cid, "1 INVITE", t)


def resp(code, text, cid, t, method="INVITE", cseq=1):
    return sip(f"SIP/2.0 {code} {text}", cid, f"{cseq} {method}", t, src=CALLEE, dst=CALLER)


def bye(cid, t):
    return sip(f"BYE sip:1001@{CALLER} SIP/2.0", cid, "2 BYE", t)


def run(tracker, packets):
    events = []
    for cp in packets:
        events.extend(tracker.feed(cp))
    return events


def finals(events):
    return {e.session.call_id: e for e in events if e.kind == "finalized"}


class TestEquivalenceWithUploadPipeline:
    """Replaying a real capture through the live tracker must classify every call
    exactly like the offline upload path does."""

    @pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
    def test_same_statuses_as_offline(self, path):
        offline = {s.call_id: s.status for s in process_pcap_sessions(parse_pcap_file(str(path)))}
        assert offline, "fixture should contain calls"

        tracker = LiveCallTracker()
        events = run(tracker, PcapReplaySource(str(path)))
        events += tracker.flush()
        live = {cid: e.session.status for cid, e in finals(events).items()}

        assert live == offline

    @pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
    def test_same_timing_as_offline(self, path):
        offline = {s.call_id: s for s in process_pcap_sessions(parse_pcap_file(str(path)))}
        tracker = LiveCallTracker()
        events = run(tracker, PcapReplaySource(str(path)))
        events += tracker.flush()
        for cid, ev in finals(events).items():
            assert ev.session.invite_time == offline[cid].invite_time
            assert ev.session.answer_time == offline[cid].answer_time
            assert ev.session.sip_result_code == offline[cid].sip_result_code


class TestCallLifecycle:
    def test_answered_call_finalises_after_bye_and_settle(self):
        t = LiveCallTracker(settle_seconds=30)
        events = run(t, [
            invite("c1", 100), resp(180, "Ringing", "c1", 101), resp(200, "OK", "c1", 105),
            bye("c1", 160),
        ])
        assert not finals(events)                 # BYE seen, but still settling
        assert t.open_call_ids == ["c1"]

        events = t.advance(160 + 29)
        assert not finals(events)
        events = t.advance(160 + 30)
        ev = finals(events)["c1"]
        assert ev.session.status == "ANSWERED" and ev.reason == "settled" and ev.terminal

    def test_answered_call_survives_long_sip_silence(self):
        """A 30-minute call produces no SIP after the ACK; it must not be closed as idle."""
        t = LiveCallTracker(idle_timeout=60)
        run(t, [invite("c1", 100), resp(180, "Ringing", "c1", 101), resp(200, "OK", "c1", 105)])
        assert not t.advance(105 + 1800)
        assert t.open_call_ids == ["c1"]

    def test_max_age_closes_a_call_that_never_ends(self):
        t = LiveCallTracker(max_call_age=3600)
        run(t, [invite("c1", 100), resp(200, "OK", "c1", 105)])
        ev = finals(t.advance(100 + 3600))["c1"]
        assert ev.reason == "max_age"

    def test_unanswered_call_closes_on_idle_timeout(self):
        t = LiveCallTracker(idle_timeout=60)
        run(t, [invite("c1", 100), resp(180, "Ringing", "c1", 101)])
        assert not t.advance(150)
        ev = finals(t.advance(101 + 60))["c1"]
        assert ev.reason == "idle_timeout" and not ev.terminal

    def test_rejected_call_becomes_terminal_on_final_failure(self):
        t = LiveCallTracker(settle_seconds=5)
        events = run(t, [invite("c1", 100), resp(180, "Ringing", "c1", 101), resp(486, "Busy Here", "c1", 103)])
        assert events[-1].terminal
        ev = finals(t.advance(103 + 5))["c1"]
        assert ev.session.status == "REJECTED" and ev.session.sip_result_code == 486

    def test_auth_challenge_is_not_terminal_and_call_continues(self):
        t = LiveCallTracker(settle_seconds=5, idle_timeout=60)
        events = run(t, [invite("c1", 100), resp(407, "Proxy Authentication Required", "c1", 100.1)])
        assert not events[-1].terminal
        run(t, [invite("c1", 100.2), resp(200, "OK", "c1", 104), bye("c1", 120)])
        ev = finals(t.advance(130))["c1"]
        assert ev.session.status == "ANSWERED"

    def test_cancel_after_ringing_is_missed(self):
        """Matches the upload pipeline: the callee rang and nobody answered -> MISSED."""
        t = LiveCallTracker(settle_seconds=5)
        run(t, [
            invite("c1", 100), resp(180, "Ringing", "c1", 101),
            sip(f"CANCEL sip:1002@{CALLEE} SIP/2.0", "c1", "1 CANCEL", 103),
            resp(200, "OK", "c1", 103.1, method="CANCEL"), resp(487, "Request Terminated", "c1", 103.2),
        ])
        assert finals(t.advance(110))["c1"].session.status == "MISSED"

    def test_cancel_before_ringing_is_cancelled(self):
        t = LiveCallTracker(settle_seconds=5)
        run(t, [
            invite("c1", 100),
            sip(f"CANCEL sip:1002@{CALLEE} SIP/2.0", "c1", "1 CANCEL", 100.5),
            resp(200, "OK", "c1", 100.6, method="CANCEL"), resp(487, "Request Terminated", "c1", 100.7),
        ])
        assert finals(t.advance(110))["c1"].session.status == "CANCELLED"


class TestFiltering:
    def test_keepalives_and_unknown_dialogs_are_ignored(self):
        t = LiveCallTracker()
        events = run(t, [
            sip("REGISTER sip:pbx SIP/2.0", "reg1", "1 REGISTER", 100),
            sip("OPTIONS sip:pbx SIP/2.0", "opt1", "1 OPTIONS", 101),
            bye("began-before-capture", 102),                       # no INVITE seen
            resp(200, "OK", "began-before-capture", 102.1, method="BYE", cseq=2),
        ])
        assert events == [] and t.open_call_ids == []

    def test_non_sip_traffic_is_ignored(self):
        t = LiveCallTracker()
        rtp = CapturedPacket(1.0, CALLER, CALLEE, 4000, 6000, "udp", b"\x80\x00" + b"\x00" * 170)
        http = CapturedPacket(1.0, CALLER, CALLEE, 1, 2, "tcp", b"NOTIFY * HTTP/1.1\r\nCall-ID: x\r\n\r\n")
        assert run(t, [rtp, http]) == []

    def test_mirror_port_duplicates_are_dropped(self):
        t = LiveCallTracker()
        inv = invite("c1", 100.0)
        dup = CapturedPacket(100.01, inv.src_ip, inv.dst_ip, inv.src_port, inv.dst_port, "udp", inv.payload)
        events = run(t, [inv, dup])
        assert len(events) == 1
        assert len(t._calls["c1"].packets) == 1

    def test_real_retransmission_is_kept(self):
        t = LiveCallTracker()
        inv = invite("c1", 100.0)
        retrans = CapturedPacket(100.5, inv.src_ip, inv.dst_ip, inv.src_port, inv.dst_port, "udp", inv.payload)
        run(t, [inv, retrans])
        assert len(t._calls["c1"].packets) == 2

    def test_stragglers_after_finalisation_do_not_reopen_the_call(self):
        t = LiveCallTracker(settle_seconds=5)
        run(t, [invite("c1", 100), resp(200, "OK", "c1", 101), bye("c1", 110)])
        assert "c1" in finals(t.advance(120))
        late = run(t, [resp(200, "OK", "c1", 121, method="BYE", cseq=2)])
        assert late == [] and t.open_call_ids == []

    def test_flush_finalises_everything_open(self):
        t = LiveCallTracker()
        run(t, [invite("a", 100), invite("b", 101)])
        events = t.flush()
        assert {e.session.call_id for e in events} == {"a", "b"}
        assert all(e.reason == "shutdown" for e in events)
        assert t.open_call_ids == []


class TestIncrementalUpdates:
    def test_status_evolves_as_packets_arrive(self):
        t = LiveCallTracker()
        e1 = run(t, [invite("c1", 100)])[-1]
        assert e1.kind == "updated" and not e1.session.has_answer
        e2 = run(t, [resp(180, "Ringing", "c1", 101)])[-1]
        assert e2.session.has_ringing
        e3 = run(t, [resp(200, "OK", "c1", 105)])[-1]
        assert e3.session.has_answer and not e3.terminal

    def test_concurrent_calls_are_tracked_independently(self):
        t = LiveCallTracker(settle_seconds=5)
        events = run(t, [
            invite("a", 100), invite("b", 100.1),
            resp(200, "OK", "a", 102), resp(486, "Busy Here", "b", 102.1),
            bye("a", 130),          # advancing the clock to 130 also settles b
        ])
        events += t.advance(140)
        done = finals(events)
        assert done["a"].session.status == "ANSWERED"
        assert done["b"].session.status == "REJECTED"
