"""
Live call tracker (v2.3.0).

Groups SIP messages from a packet stream into calls, re-classifies each call
with the existing state machine as packets arrive, and decides when a call is
finished. Pure logic: no database, no sockets, no wall clock of its own. Time
comes from packet timestamps (and from tick() in live mode), so a replayed
capture behaves exactly like live traffic and tests are deterministic.

Lifecycle of a tracked call
  * Tracking starts at the first INVITE. Anything else for an unknown Call-ID
    (REGISTER/OPTIONS keepalives, the tail of a call that began before capture
    started) is ignored.
  * A call is TERMINAL once a BYE, a CANCEL, or a final failure response to the
    INVITE (>= 300, except 401/407 auth challenges) has been seen.
  * Terminal calls are finalised after `settle_seconds` with no further packets,
    which lets retransmissions and the 487/ACK/200-to-BYE exchange finish.
  * Calls that never became terminal are finalised after `idle_timeout` of
    silence ONLY if they were never answered. An answered call is silent on SIP
    for its whole duration, so it stays open until BYE.
  * Media liveness: the caller reports RTP with note_media(). An answered call
    whose media was seen but then stopped for `media_idle_timeout` (and with no
    SIP either) is finalised as "media_stopped", which catches a missed BYE.
    Calls whose media was never seen (e.g. RTP not on the mirror port) are NOT
    closed this way, so they cannot be cut off wrongly.
  * `max_call_age` is a hard backstop for everything.

Limitations: SIP over TCP is parsed one message per segment (no stream
reassembly yet); IPv4/IPv6 UDP is the supported path.
"""
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from app.capture.packet_source import CapturedPacket
from app.core.call_state_machine import CallSession, classify_session
from app.core.sip_parser import SIPPacket, build_sip_packet

logger = logging.getLogger(__name__)

AUTH_CHALLENGES = {401, 407}
DUPLICATE_WINDOW = 0.05          # seconds: mirror-port duplicates arrive back to back
FINALISED_MEMORY = 600.0         # seconds to remember finished Call-IDs (ignore stragglers)


@dataclass
class TrackerEvent:
    kind: str                     # "updated" | "finalized"
    session: CallSession          # freshly classified from all packets so far
    terminal: bool                # BYE / CANCEL / final failure already seen
    reason: Optional[str] = None  # settled | idle_timeout | media_stopped | max_age | shutdown


class _Tracked:
    __slots__ = ("call_id", "packets", "first_ts", "last_ts", "terminal", "answered", "seen",
                 "last_media_ts")

    def __init__(self, call_id: str, ts: float):
        self.call_id = call_id
        self.packets: list[SIPPacket] = []
        self.first_ts = ts
        self.last_ts = ts
        self.terminal = False
        self.answered = False
        self.last_media_ts: Optional[float] = None
        self.seen: dict[str, float] = {}   # duplicate-detection hash -> last timestamp


def _is_terminal_packet(p: SIPPacket) -> bool:
    if p.is_request and p.method in ("BYE", "CANCEL"):
        return True
    return bool(
        p.is_response
        and (p.cseq_method or "").upper() == "INVITE"
        and p.response_code is not None
        and p.response_code >= 300
        and p.response_code not in AUTH_CHALLENGES
    )


def _is_answer_packet(p: SIPPacket) -> bool:
    return bool(
        p.is_response
        and (p.cseq_method or "").upper() == "INVITE"
        and p.response_code is not None
        and 200 <= p.response_code < 300
    )


class LiveCallTracker:
    def __init__(
        self,
        settle_seconds: float = 30.0,
        idle_timeout: float = 60.0,
        max_call_age: float = 4 * 3600.0,
        media_idle_timeout: float = 120.0,
    ):
        self.settle_seconds = settle_seconds
        self.idle_timeout = idle_timeout
        self.media_idle_timeout = media_idle_timeout
        self.max_call_age = max_call_age
        self._calls: dict[str, _Tracked] = {}
        self._finalised: dict[str, float] = {}
        self._clock = 0.0

    # ── public API ────────────────────────────────────────────────────────
    @property
    def open_call_ids(self) -> list[str]:
        return list(self._calls)

    def feed(self, cp: CapturedPacket) -> list[TrackerEvent]:
        """Process one captured packet; returns events for this packet plus any expiries."""
        events: list[TrackerEvent] = []
        self._clock = max(self._clock, cp.timestamp)

        event = self._ingest(cp)
        if event:
            events.append(event)
        events.extend(self.advance(self._clock))
        return events

    def note_media(self, call_id: str, timestamp: float) -> None:
        """Record that RTP for this call was seen at `timestamp` (see RTPSpooler.feed)."""
        tracked = self._calls.get(call_id)
        if tracked is not None:
            tracked.last_media_ts = max(tracked.last_media_ts or 0.0, timestamp)
            self._clock = max(self._clock, timestamp)

    def advance(self, now: float) -> list[TrackerEvent]:
        """Move the clock forward (use time.time() in live mode) and finalise what has expired."""
        self._clock = max(self._clock, now)
        events: list[TrackerEvent] = []

        for cid in list(self._calls):
            t = self._calls[cid]
            reason = None
            if now - t.first_ts >= self.max_call_age:
                reason = "max_age"
            elif t.terminal and now - t.last_ts >= self.settle_seconds:
                reason = "settled"
            elif not t.terminal and not t.answered and now - t.last_ts >= self.idle_timeout:
                reason = "idle_timeout"
            elif (
                not t.terminal and t.answered and t.last_media_ts is not None
                and now - max(t.last_ts, t.last_media_ts) >= self.media_idle_timeout
            ):
                reason = "media_stopped"
            if reason:
                events.append(self._finalise(cid, reason))

        for cid in [c for c, ts in self._finalised.items() if now - ts > FINALISED_MEMORY]:
            del self._finalised[cid]
        return events

    def flush(self) -> list[TrackerEvent]:
        """Finalise every open call (shutdown or end of a replayed capture)."""
        return [self._finalise(cid, "shutdown") for cid in list(self._calls)]

    # ── internals ─────────────────────────────────────────────────────────
    def _ingest(self, cp: CapturedPacket) -> Optional[TrackerEvent]:
        text = cp.payload.decode("utf-8", errors="replace")
        pkt = build_sip_packet(
            text, cp.timestamp, cp.src_ip, cp.dst_ip, cp.src_port, cp.dst_port
        )
        if pkt is None:
            return None

        cid = pkt.call_id.strip()
        pkt.call_id = cid

        if cid in self._finalised:
            return None  # straggler for a call we already closed

        tracked = self._calls.get(cid)
        if tracked is None:
            if not (pkt.is_request and pkt.method == "INVITE"):
                return None  # not a call we saw start (keepalive, or began before capture)
            tracked = _Tracked(cid, cp.timestamp)
            self._calls[cid] = tracked

        if self._is_duplicate(tracked, cp):
            return None

        tracked.packets.append(pkt)
        tracked.last_ts = max(tracked.last_ts, cp.timestamp)
        if _is_terminal_packet(pkt):
            tracked.terminal = True
        if _is_answer_packet(pkt):
            tracked.answered = True

        return TrackerEvent("updated", self._classify(tracked), tracked.terminal)

    @staticmethod
    def _is_duplicate(tracked: _Tracked, cp: CapturedPacket) -> bool:
        """A mirror port can deliver the same frame twice; real retransmissions are later."""
        key = hashlib.blake2b(
            f"{cp.src_ip}|{cp.src_port}|{cp.dst_ip}|{cp.dst_port}|".encode() + cp.payload,
            digest_size=12,
        ).hexdigest()
        previous = tracked.seen.get(key)
        tracked.seen[key] = cp.timestamp
        return previous is not None and 0 <= cp.timestamp - previous <= DUPLICATE_WINDOW

    @staticmethod
    def _classify(tracked: _Tracked) -> CallSession:
        # A fresh session per classification keeps the state machine stateless,
        # so live and file processing share exactly the same rules.
        return classify_session(CallSession(call_id=tracked.call_id, packets=list(tracked.packets)))

    def _finalise(self, cid: str, reason: str) -> TrackerEvent:
        tracked = self._calls.pop(cid)
        self._finalised[cid] = self._clock
        return TrackerEvent("finalized", self._classify(tracked), tracked.terminal, reason)
