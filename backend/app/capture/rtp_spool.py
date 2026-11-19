"""
RTP spooler (v2.3.0).

Matches live RTP to calls through the SDP addresses announced in SIP, and
appends each packet to a per-call spool file on disk, so a long call never sits
in memory. When the call ends, load() reads the spool back as RTPPacket lists
for audio reconstruction and quality metrics.

Matching mirrors the offline analysis (rtp_analyzer.correlate): a packet belongs
to a call when its SOURCE ip:port equals the address in that call's SDP. The
caller's SDP gives the caller-to-callee direction, the callee's SDP the reverse.

Spool record (big endian, fixed header + payload):
    timestamp f64 | direction u8 | payload_type u8 | seq u16 | rtp_ts u32 | ssrc u32 | length u16 | payload
"""
import hashlib
import logging
import os
import struct
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app.capture.packet_source import CapturedPacket
from app.core.rtp_analyzer import CallSDP, RTPPacket, _parse_rtp_header

logger = logging.getLogger(__name__)

_RECORD = struct.Struct(">dBBHIIH")
DIR_CALLER_TO_CALLEE = 0
DIR_CALLEE_TO_CALLER = 1
DTMF_PAYLOAD_TYPE = 101          # telephone-event, skipped like the offline analysis
RTCP_PAYLOAD_TYPES = range(72, 80)  # 200-204 with the marker bit masked off
DEDUP_WINDOW = 512               # sequence numbers remembered per stream


@dataclass
class SpoolData:
    a2b: list[RTPPacket]
    b2a: list[RTPPacket]
    ptime_ms: int
    total_packets: int


@dataclass
class _CallSpool:
    path: str
    handle: object
    endpoints: dict = field(default_factory=dict)   # (ip, port) -> direction
    ptime_ms: int = 20
    packets: int = 0
    last_media_ts: Optional[float] = None
    since_flush: int = 0
    recent: dict = field(default_factory=dict)      # (direction, ssrc) -> (deque, set)


class RTPSpooler:
    def __init__(self, spool_dir: str, flush_every: int = 200):
        self.spool_dir = spool_dir
        self.flush_every = flush_every
        self._calls: dict[str, _CallSpool] = {}
        self._endpoint_owner: dict[tuple, str] = {}     # (ip, port) -> call_id
        os.makedirs(spool_dir, exist_ok=True)

    # ── registration ──────────────────────────────────────────────────────
    def update_sdp(self, call_id: str, sdp: CallSDP) -> None:
        """Register (or refresh) the media endpoints of a call. Safe to call repeatedly."""
        endpoints = {}
        if sdp.caller_sdp:
            endpoints[(sdp.caller_sdp.ip, sdp.caller_sdp.port)] = DIR_CALLER_TO_CALLEE
        if sdp.callee_sdp:
            endpoints[(sdp.callee_sdp.ip, sdp.callee_sdp.port)] = DIR_CALLEE_TO_CALLER
        if not endpoints:
            return

        spool = self._calls.get(call_id)
        if spool is None:
            path = os.path.join(
                self.spool_dir, hashlib.blake2b(call_id.encode(), digest_size=10).hexdigest() + ".spool"
            )
            spool = _CallSpool(path=path, handle=open(path, "ab"))
            self._calls[call_id] = spool

        for key in list(spool.endpoints):               # a re-INVITE may move the media
            if key not in endpoints and self._endpoint_owner.get(key) == call_id:
                del self._endpoint_owner[key]
        spool.endpoints = endpoints
        for key in endpoints:
            self._endpoint_owner[key] = call_id
        media = sdp.caller_sdp or sdp.callee_sdp
        spool.ptime_ms = media.ptime_ms

    def has_call(self, call_id: str) -> bool:
        return call_id in self._calls

    def packet_count(self, call_id: str) -> int:
        spool = self._calls.get(call_id)
        return spool.packets if spool else 0

    def last_media_time(self, call_id: str) -> Optional[float]:
        spool = self._calls.get(call_id)
        return spool.last_media_ts if spool else None

    # ── ingest ────────────────────────────────────────────────────────────
    def feed(self, cp: CapturedPacket) -> Optional[str]:
        """Spool the packet if it is RTP for a registered call; returns that call_id, else None."""
        if cp.protocol != "udp":
            return None
        call_id = self._endpoint_owner.get((cp.src_ip, cp.src_port))
        if call_id is None:
            return None
        spool = self._calls[call_id]

        parsed = _parse_rtp_header(cp.payload)
        if parsed is None:
            return None
        _, pt, seq, rtp_ts, ssrc, offset = parsed
        if pt == DTMF_PAYLOAD_TYPE or pt in RTCP_PAYLOAD_TYPES:
            return None

        direction = spool.endpoints[(cp.src_ip, cp.src_port)]
        if self._is_duplicate(spool, direction, ssrc, seq):
            return None

        payload = cp.payload[offset:]
        spool.handle.write(
            _RECORD.pack(cp.timestamp, direction, pt, seq, rtp_ts, ssrc, len(payload)) + payload
        )
        spool.packets += 1
        spool.last_media_ts = cp.timestamp
        spool.since_flush += 1
        if spool.since_flush >= self.flush_every:
            spool.handle.flush()
            spool.since_flush = 0
        return call_id

    @staticmethod
    def _is_duplicate(spool: _CallSpool, direction: int, ssrc: int, seq: int) -> bool:
        """RTP is never retransmitted, so a repeated (ssrc, seq) is a mirror-port duplicate."""
        window, seen = spool.recent.setdefault((direction, ssrc), (deque(maxlen=DEDUP_WINDOW), set()))
        if seq in seen:
            return True
        if len(window) == window.maxlen:
            seen.discard(window[0])
        window.append(seq)
        seen.add(seq)
        return False

    # ── read back / cleanup ───────────────────────────────────────────────
    def load(self, call_id: str) -> Optional[SpoolData]:
        """Read the call's spooled packets back (payloads included). None if unknown call."""
        spool = self._calls.get(call_id)
        if spool is None:
            return None
        spool.handle.flush()

        a2b: list[RTPPacket] = []
        b2a: list[RTPPacket] = []
        with open(spool.path, "rb") as f:
            while True:
                head = f.read(_RECORD.size)
                if len(head) < _RECORD.size:
                    break                       # clean end (or a torn final record)
                ts, direction, pt, seq, rtp_ts, ssrc, length = _RECORD.unpack(head)
                payload = f.read(length)
                if len(payload) < length:
                    break
                (src_ip, src_port), (dst_ip, dst_port) = self._addresses(spool, direction)
                pkt = RTPPacket(ts, seq, ssrc, pt, rtp_ts, src_ip, src_port, dst_ip, dst_port, payload)
                (a2b if direction == DIR_CALLER_TO_CALLEE else b2a).append(pkt)

        return SpoolData(a2b=a2b, b2a=b2a, ptime_ms=spool.ptime_ms, total_packets=len(a2b) + len(b2a))

    @staticmethod
    def _addresses(spool: _CallSpool, direction: int):
        """(source, destination) of a direction, from the SDP endpoints (destination = the other side)."""
        by_dir = {d: key for key, d in spool.endpoints.items()}
        src = by_dir.get(direction, ("", 0))
        dst = by_dir.get(1 - direction, ("", 0))
        return src, dst

    def close_call(self, call_id: str, delete: bool = True) -> None:
        spool = self._calls.pop(call_id, None)
        if spool is None:
            return
        for key in spool.endpoints:
            if self._endpoint_owner.get(key) == call_id:
                del self._endpoint_owner[key]
        try:
            spool.handle.close()
        finally:
            if delete:
                try:
                    os.unlink(spool.path)
                except OSError as e:
                    logger.warning(f"Could not remove spool {spool.path}: {e}")

    def close_all(self, delete: bool = True) -> None:
        for call_id in list(self._calls):
            self.close_call(call_id, delete=delete)
