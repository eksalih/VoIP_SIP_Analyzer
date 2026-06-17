"""
SIP Call State Machine
Processes SIP packets and determines call outcome (ANSWERED / MISSED / REJECTED / CANCELLED / FAILED).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.sip_parser import SIPPacket

logger = logging.getLogger(__name__)

# SIP response code buckets
# NOTE: 487 is intentionally excluded — it is the normal response to CANCEL, not a rejection
REJECTION_CODES = {486, 603, 600, 480}
BUSY_CODES = {486, 600}
DECLINE_CODES = {603}
UNAVAILABLE_CODES = {480}
FAILURE_CODES = {400, 401, 403, 404, 405, 407, 408, 410, 415, 420, 421,
                  423, 481, 482, 483, 484, 485, 488, 489, 491, 493,
                  500, 501, 502, 503, 504, 505, 513,
                  600, 603, 604, 606}

# Methods that indicate a real call session (filter out pure REGISTER/OPTIONS ghost sessions)
CALL_METHODS = {"INVITE", "BYE", "CANCEL", "ACK", "PRACK", "UPDATE", "REFER", "INFO"}


@dataclass
class CallSession:
    call_id: str
    packets: list[SIPPacket] = field(default_factory=list)

    # Extracted metadata (from first INVITE)
    caller: Optional[str] = None
    called: Optional[str] = None
    display_name: Optional[str] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    user_agent: Optional[str] = None
    sip_domain: Optional[str] = None
    branch_id: Optional[str] = None

    # Timing
    invite_time: Optional[datetime] = None
    ringing_time: Optional[datetime] = None
    answer_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # State flags
    has_invite: bool = False
    has_trying: bool = False
    has_ringing: bool = False
    has_answer: bool = False
    has_bye: bool = False
    has_cancel: bool = False
    has_ack: bool = False

    # Rejection info
    rejection_code: Optional[int] = None
    rejection_reason: Optional[str] = None

    # Final determined status
    status: Optional[str] = None
    sip_result_code: Optional[int] = None

    @property
    def ring_duration(self) -> Optional[float]:
        if self.ringing_time and self.answer_time:
            return (self.answer_time - self.ringing_time).total_seconds()
        if self.ringing_time and self.end_time:
            return (self.end_time - self.ringing_time).total_seconds()
        if self.invite_time and self.end_time and not self.has_ringing:
            return (self.end_time - self.invite_time).total_seconds()
        return None

    @property
    def talk_duration(self) -> Optional[float]:
        if self.answer_time and self.end_time:
            d = (self.end_time - self.answer_time).total_seconds()
            return d if d >= 0 else None
        return None

    @property
    def total_duration(self) -> Optional[float]:
        if self.invite_time and self.end_time:
            return (self.end_time - self.invite_time).total_seconds()
        return None


def group_packets_by_call(packets: list[SIPPacket]) -> dict[str, CallSession]:
    """Group SIP packets by Call-ID into sessions."""
    sessions: dict[str, CallSession] = {}
    for pkt in packets:
        if not pkt.call_id:
            continue
        cid = pkt.call_id.strip()
        if cid not in sessions:
            sessions[cid] = CallSession(call_id=cid)
        sessions[cid].packets.append(pkt)
    return sessions


def _is_call_session(session: CallSession) -> bool:
    """
    Return True only if this session contains actual call traffic (INVITE).
    Filters out pure REGISTER/OPTIONS/NOTIFY keepalive sessions that Etisalat
    and other carriers send alongside call sessions with separate Call-IDs.
    """
    for pkt in session.packets:
        if (pkt.method or "").upper() == "INVITE":
            return True
    return False


def _pick_first(pkt: SIPPacket, session: CallSession, attr: str):
    """Set session attribute from packet only if not yet set."""
    if getattr(session, attr) is None:
        val = getattr(pkt, attr, None)
        if val:
            setattr(session, attr, val)


def classify_session(session: CallSession) -> CallSession:
    """
    Run the SIP state machine over a session's packets and determine call status.
    Packets are sorted in chronological order before processing.
    """
    # Sort packets by timestamp
    pkts = sorted(
        [p for p in session.packets if p.timestamp],
        key=lambda x: x.timestamp,
    )
    # Append any packets without timestamps at the end
    pkts += [p for p in session.packets if not p.timestamp]

    for pkt in pkts:
        method = (pkt.method or "").upper()
        code = pkt.response_code

        # ── Requests ──────────────────────────────────────────────────────────

        if method == "INVITE" and not session.has_invite:
            session.has_invite = True
            session.invite_time = pkt.timestamp
            _pick_first(pkt, session, "caller")
            _pick_first(pkt, session, "called")
            _pick_first(pkt, session, "display_name")
            _pick_first(pkt, session, "source_ip")
            _pick_first(pkt, session, "destination_ip")
            _pick_first(pkt, session, "user_agent")
            _pick_first(pkt, session, "sip_domain")
            _pick_first(pkt, session, "branch_id")

        elif method == "ACK":
            session.has_ack = True

        elif method == "BYE":
            session.has_bye = True
            if pkt.timestamp:
                session.end_time = pkt.timestamp

        elif method == "CANCEL":
            session.has_cancel = True
            if pkt.timestamp and not session.end_time:
                session.end_time = pkt.timestamp

        # ── Responses ─────────────────────────────────────────────────────────

        elif pkt.is_response and code:

            if code == 100:
                session.has_trying = True

            elif code in (180, 183):
                if not session.has_ringing:
                    session.has_ringing = True
                    session.ringing_time = pkt.timestamp

            elif code == 200:
                # Critical: A 200 OK that is the response to a CANCEL request
                # must NOT be counted as the call being answered.
                # We only mark the call answered when:
                #   • an INVITE is in progress (has_invite=True)
                #   • AND the caller has NOT already sent CANCEL
                if not session.has_answer and session.has_invite and not session.has_cancel:
                    session.has_answer = True
                    session.answer_time = pkt.timestamp
                    session.sip_result_code = 200

            elif code == 487:
                # 487 Request Terminated — the UA's confirmation that CANCEL was processed.
                # This is part of the normal MISSED call flow, not a rejection.
                # Set end_time only; _determine_status() handles classification via has_cancel.
                if not session.end_time and pkt.timestamp:
                    session.end_time = pkt.timestamp
                # Explicitly do NOT set rejection_code here.

            elif code in REJECTION_CODES or (400 <= code < 700):
                # Hard rejection or signaling failure
                if not session.rejection_code:
                    session.rejection_code = code
                    session.rejection_reason = pkt.response_text or _code_to_reason(code)
                if not session.end_time and pkt.timestamp:
                    session.end_time = pkt.timestamp
                session.sip_result_code = code

    # Ensure start time is set even for incomplete captures
    if not session.invite_time and pkts:
        session.invite_time = pkts[0].timestamp

    # Determine final status
    session.status = _determine_status(session)
    return session


def _determine_status(s: CallSession) -> str:
    """
    Apply call classification rules in priority order:
      ANSWERED  — call was established (200 OK received before any CANCEL)
      REJECTED  — user actively declined (486 Busy Here / 603 Decline / 600 Busy Everywhere)
      MISSED    — rang but caller hung up (CANCEL after 180 Ringing)
      CANCELLED — caller cancelled before it even rang
      FAILED    — SIP signaling error
      UNKNOWN   — not enough information
    """
    # 1. Answered takes highest priority
    if s.has_answer:
        return "ANSWERED"

    # 2. Explicit user rejection codes
    if s.rejection_code and s.rejection_code in REJECTION_CODES:
        return "REJECTED"

    # 3. CANCEL flow — MISSED if it rang, CANCELLED if it never rang
    if s.has_cancel:
        if s.has_ringing:
            return "MISSED"
        return "CANCELLED"

    # 4. Rang but no CANCEL and no answer — unanswered timeout
    if s.has_invite and s.has_ringing and not s.has_answer:
        return "MISSED"

    # 5. Signaling error (non-rejection 4xx/5xx)
    if s.rejection_code and 400 <= s.rejection_code < 700:
        return "FAILED"

    if s.has_invite and not s.has_answer:
        return "FAILED"

    return "UNKNOWN"


def _code_to_reason(code: int) -> str:
    reasons = {
        486: "Busy Here",
        603: "Decline",
        600: "Busy Everywhere",
        480: "Temporarily Unavailable",
        487: "Request Terminated",
        404: "Not Found",
        408: "Request Timeout",
        503: "Service Unavailable",
        500: "Server Internal Error",
        403: "Forbidden",
        401: "Unauthorized",
    }
    return reasons.get(code, f"SIP {code}")


def process_pcap_sessions(packets: list[SIPPacket]) -> list[CallSession]:
    """
    Full pipeline: group packets → filter non-call sessions → classify each session.
    Ghost sessions (REGISTER/OPTIONS keepalives) are excluded from results.
    """
    all_sessions = group_packets_by_call(packets)
    results = []

    for cid, session in all_sessions.items():
        # Skip REGISTER/OPTIONS keepalive sessions — they are not calls
        if not _is_call_session(session):
            logger.debug(f"Skipping non-call session: {cid}")
            continue

        try:
            classified = classify_session(session)
            results.append(classified)
        except Exception as e:
            logger.error(f"Error classifying session {cid}: {e}")
            session.status = "FAILED"
            results.append(session)

    # Sort by call start time
    results.sort(key=lambda s: s.invite_time or datetime.min)
    logger.info(f"Classified {len(results)} call sessions (excluded non-call sessions)")
    return results
