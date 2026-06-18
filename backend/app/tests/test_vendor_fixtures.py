"""
Real-world vendor fixture regression tests.

Unlike test_sip_engine.py (synthetic packets) and test_api.py (synthetic PCAPs),
these tests run the full parser + classification engine against actual PCAP
captures taken from a real Yeastar PBX, to catch vendor-specific SIP quirks
that hand-built test data can't surface.

If you add fixtures from another vendor, follow the same pattern: capture real
traffic, manually verify the expected outcome by reading the raw SIP flow, then
assert the engine reproduces it. This is what caught the original ghost-session
and CANCEL/200-OK bugs against Etisalat traffic — multi-vendor real captures
are the best defense against vendor-specific regressions.
"""
import os
import pytest

from app.core.sip_parser import parse_pcap_file
from app.core.call_state_machine import process_pcap_sessions

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "yeastar")


def _classify(filename: str):
    path = os.path.join(FIXTURES_DIR, filename)
    packets = parse_pcap_file(path)
    return process_pcap_sessions(packets)


class TestYeastarAnswered:
    """answered_clean.pcapng: a single clean INVITE -> 200 OK -> BYE call."""

    def test_single_call_found(self):
        sessions = _classify("answered_clean.pcapng")
        assert len(sessions) == 1

    def test_classified_as_answered(self):
        sessions = _classify("answered_clean.pcapng")
        assert sessions[0].status == "ANSWERED"

    def test_durations_are_positive_and_sane(self):
        sessions = _classify("answered_clean.pcapng")
        s = sessions[0]
        assert s.ring_duration is not None and s.ring_duration > 0
        assert s.talk_duration is not None and s.talk_duration > 0
        assert s.total_duration is not None and s.total_duration > s.talk_duration


class TestYeastarMissed:
    """missed_call.pcapng: INVITE -> 180 Ringing -> CANCEL -> 487, no answer."""

    def test_single_call_found(self):
        sessions = _classify("missed_clean.pcapng")
        assert len(sessions) == 1

    def test_classified_as_missed(self):
        sessions = _classify("missed_clean.pcapng")
        assert sessions[0].status == "MISSED"

    def test_no_talk_duration(self):
        """A call that never connects must not report a talk duration."""
        sessions = _classify("missed_clean.pcapng")
        assert sessions[0].talk_duration is None


class TestYeastarMixedCancelThenAnswered:
    """
    mixed_cancel_then_answered.pcapng: two distinct call attempts in one file.
    Call 1: rings, then CANCELled (-> MISSED).
    Call 2: a separate INVITE that is fully answered and ends with BYE (-> ANSWERED).
    This is the scenario that also contains REGISTER/401/REGISTER/200 auth challenge
    traffic and OPTIONS keepalives mixed in -- both must be excluded as ghost sessions.
    """

    def test_exactly_two_real_calls_found(self):
        """REGISTER and OPTIONS keepalive traffic in this capture must not produce
        extra ghost sessions alongside the two real calls."""
        sessions = _classify("mixed_cancel_then_answered.pcapng")
        assert len(sessions) == 2

    def test_one_missed_one_answered(self):
        sessions = _classify("mixed_cancel_then_answered.pcapng")
        statuses = sorted(s.status for s in sessions)
        assert statuses == ["ANSWERED", "MISSED"]

    def test_calls_have_distinct_call_ids(self):
        sessions = _classify("mixed_cancel_then_answered.pcapng")
        call_ids = {s.call_id for s in sessions}
        assert len(call_ids) == 2


class TestYeastarMixedRejectedAndCancelled:
    """
    mixed_rejected_and_cancelled.pcapng: four call attempts in one file.
    Three end in 486 Busy Here (-> REJECTED), one ends in CANCEL after
    ringing (-> MISSED). This is the key test that REJECTED and MISSED
    are never merged, even when both appear repeatedly in the same capture.
    """

    def test_four_calls_found(self):
        sessions = _classify("mixed_rejected_and_cancelled.pcapng")
        assert len(sessions) == 4

    def test_three_rejected_one_missed(self):
        sessions = _classify("mixed_rejected_and_cancelled.pcapng")
        statuses = sorted(s.status for s in sessions)
        assert statuses == ["MISSED", "REJECTED", "REJECTED", "REJECTED"]

    def test_rejected_calls_carry_486_busy_here(self):
        sessions = _classify("mixed_rejected_and_cancelled.pcapng")
        rejected = [s for s in sessions if s.status == "REJECTED"]
        assert len(rejected) == 3
        for s in rejected:
            assert s.rejection_code == 486
            assert s.rejection_reason == "Busy Here"

    def test_missed_call_has_no_rejection_code(self):
        """The CANCELled call in this file must not be confused with the
        REJECTED calls just because they're in the same capture."""
        sessions = _classify("mixed_rejected_and_cancelled.pcapng")
        missed = [s for s in sessions if s.status == "MISSED"]
        assert len(missed) == 1
        assert missed[0].rejection_code is None


class TestYeastarCombinedSummary:
    """
    Sanity check: across all four Yeastar fixtures combined, the engine should
    find 8 total real calls with a 2/3/3 ANSWERED/MISSED/REJECTED split,
    matching what was manually verified against the raw SIP captures.
    """

    def test_combined_call_count_and_status_breakdown(self):
        all_sessions = []
        for fname in [
            "answered_clean.pcapng",
            "missed_clean.pcapng",
            "mixed_cancel_then_answered.pcapng",
            "mixed_rejected_and_cancelled.pcapng",
        ]:
            all_sessions.extend(_classify(fname))

        assert len(all_sessions) == 8

        counts = {}
        for s in all_sessions:
            counts[s.status] = counts.get(s.status, 0) + 1

        assert counts.get("ANSWERED") == 2
        assert counts.get("MISSED") == 3
        assert counts.get("REJECTED") == 3
        assert counts.get("FAILED") is None
        assert counts.get("CANCELLED") is None
