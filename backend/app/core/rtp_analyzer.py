"""
RTP Analyzer
Parses RTP media streams from a PCAP file, correlates them to SIP calls
via SDP negotiation, and computes per-stream quality metrics:

  - Packet loss  (gap detection in RTP sequence numbers)
  - Jitter       (mean absolute inter-arrival time deviation, RFC 3550 inspired)
  - One-way audio (one direction has packets, the other has zero)
  - Codec        (from SDP payload type mapping)

Additive only — never changes SIP call classification.
Calls without RTP (MISSED, REJECTED, CANCELLED) simply get no RTPStream rows.
"""
import re
import logging
import struct
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Codec map (RFC 3551 static assignments + common extensions) ───────────
PT_CODEC_MAP: dict[int, str] = {
    0:   "PCMU/8000",
    3:   "GSM/8000",
    4:   "G723/8000",
    7:   "LPC/8000",
    8:   "PCMA/8000",
    9:   "G722/8000",
    10:  "L16/44100/2",
    11:  "L16/44100",
    13:  "CN/8000",
    14:  "MPA/90000",
    15:  "G728/8000",
    18:  "G729/8000",
    26:  "JPEG/90000",
    31:  "H261/90000",
    34:  "H263/90000",
    99:  "H264/90000",
    101: "telephone-event/8000",
}

SDP_CONNECTION_RE = re.compile(r'^c=IN IP[46] (\S+)', re.MULTILINE)
SDP_MEDIA_RE      = re.compile(r'^m=audio (\d+) RTP/\S+ (.+)', re.MULTILINE)
SDP_RTPMAP_RE     = re.compile(r'^a=rtpmap:(\d+) ([^\s/]+/\d+)', re.MULTILINE)
SDP_PTIME_RE      = re.compile(r'^a=ptime:(\d+)', re.MULTILINE)


# ── SDP parsing ───────────────────────────────────────────────────────────

@dataclass
class SDPMediaDesc:
    ip: str
    port: int
    payload_types: list[int] = field(default_factory=list)
    codec_map: dict[int, str] = field(default_factory=dict)
    ptime_ms: int = 20


def parse_sdp(sip_raw: str) -> Optional[SDPMediaDesc]:
    """Extract the first audio media description from a SIP message's SDP body."""
    if "\r\n\r\n" in sip_raw:
        sdp = sip_raw.split("\r\n\r\n", 1)[1]
    elif "\n\n" in sip_raw:
        sdp = sip_raw.split("\n\n", 1)[1]
    else:
        return None

    c_match = SDP_CONNECTION_RE.search(sdp)
    if not c_match:
        return None
    ip = c_match.group(1)

    m_match = SDP_MEDIA_RE.search(sdp)
    if not m_match:
        return None

    port = int(m_match.group(1))
    if port == 0:
        return None  # port=0 means media rejected/inactive

    pts = []
    for pt_str in m_match.group(2).split():
        try:
            pts.append(int(pt_str))
        except ValueError:
            pass

    codec_map: dict[int, str] = {}
    for rtpmap in SDP_RTPMAP_RE.finditer(sdp):
        pt = int(rtpmap.group(1))
        codec_map[pt] = rtpmap.group(2)

    for pt in pts:
        if pt not in codec_map and pt in PT_CODEC_MAP:
            codec_map[pt] = PT_CODEC_MAP[pt]

    ptime_match = SDP_PTIME_RE.search(sdp)
    ptime = int(ptime_match.group(1)) if ptime_match else 20

    return SDPMediaDesc(ip=ip, port=port, payload_types=pts,
                        codec_map=codec_map, ptime_ms=ptime)


# ── RTP packet extraction ─────────────────────────────────────────────────

@dataclass
class RTPPacket:
    timestamp_epoch: float
    sequence: int
    ssrc: int
    payload_type: int
    rtp_timestamp: int
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int


def _parse_rtp_header(payload: bytes) -> Optional[tuple]:
    if len(payload) < 12:
        return None
    version = (payload[0] >> 6) & 0x03
    if version != 2:
        return None
    pt   = payload[1] & 0x7F
    seq  = struct.unpack(">H", payload[2:4])[0]
    ts   = struct.unpack(">I", payload[4:8])[0]
    ssrc = struct.unpack(">I", payload[8:12])[0]
    return (version, pt, seq, ts, ssrc)


def extract_rtp_packets(file_path: str) -> list[RTPPacket]:
    """Read all RTP v2 packets from the PCAP."""
    try:
        from scapy.all import rdpcap, UDP, IP, Raw
    except ImportError:
        logger.error("Scapy not available for RTP extraction")
        return []

    packets: list[RTPPacket] = []
    try:
        for pkt in rdpcap(file_path):
            if not (pkt.haslayer(UDP) and pkt.haslayer(IP) and pkt.haslayer(Raw)):
                continue
            payload = pkt[Raw].load
            parsed = _parse_rtp_header(payload)
            if parsed is None:
                continue
            _, pt, seq, ts, ssrc = parsed
            if pt == 101:
                continue  # skip DTMF
            packets.append(RTPPacket(
                timestamp_epoch=float(pkt.time),
                sequence=seq,
                ssrc=ssrc,
                payload_type=pt,
                rtp_timestamp=ts,
                source_ip=pkt[IP].src,
                source_port=pkt[UDP].sport,
                destination_ip=pkt[IP].dst,
                destination_port=pkt[UDP].dport,
            ))
    except Exception as e:
        logger.error(f"RTP extraction error: {e}")

    return packets


# ── Quality metrics ───────────────────────────────────────────────────────

@dataclass
class RTPStreamMetrics:
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    ssrc: str
    payload_type: int
    codec: str
    packet_count: int
    packet_loss_count: int
    packet_loss_pct: float
    jitter_ms: float
    jitter_max_ms: float
    duration_seconds: float
    expected_packets: Optional[int]
    is_one_way: bool = False


def _compute_metrics(packets: list[RTPPacket], ptime_ms: int = 20) -> RTPStreamMetrics:
    packets = sorted(packets, key=lambda p: p.timestamp_epoch)
    n = len(packets)
    first_seq, last_seq = packets[0].sequence, packets[-1].sequence

    # Sequence span with 16-bit wrap-around
    span = (65536 - first_seq + last_seq + 1) if last_seq < first_seq else (last_seq - first_seq + 1)
    lost = max(0, span - n)
    loss_pct = round(lost / span * 100, 2) if span > 0 else 0.0

    duration = packets[-1].timestamp_epoch - packets[0].timestamp_epoch
    expected = int(duration / (ptime_ms / 1000)) + 1 if duration > 0 else n

    # Jitter: mean absolute inter-arrival deviation
    jitter_samples = []
    clock_rate = 8000
    for i in range(1, n):
        arrival_diff = (packets[i].timestamp_epoch - packets[i-1].timestamp_epoch) * 1000
        rtp_diff_raw = (packets[i].rtp_timestamp - packets[i-1].rtp_timestamp) % (2**32)
        rtp_diff_ms  = (rtp_diff_raw / clock_rate) * 1000
        jitter_samples.append(abs(arrival_diff - rtp_diff_ms))

    jitter_mean = round(sum(jitter_samples) / len(jitter_samples), 3) if jitter_samples else 0.0
    jitter_max  = round(max(jitter_samples), 3) if jitter_samples else 0.0

    pt    = packets[0].payload_type
    codec = PT_CODEC_MAP.get(pt, f"PT{pt}")

    return RTPStreamMetrics(
        source_ip=packets[0].source_ip,
        source_port=packets[0].source_port,
        destination_ip=packets[0].destination_ip,
        destination_port=packets[0].destination_port,
        ssrc=hex(packets[0].ssrc),
        payload_type=pt,
        codec=codec,
        packet_count=n,
        packet_loss_count=lost,
        packet_loss_pct=loss_pct,
        jitter_ms=jitter_mean,
        jitter_max_ms=jitter_max,
        duration_seconds=round(duration, 3),
        expected_packets=expected,
    )


# ── SDP correlation ───────────────────────────────────────────────────────

@dataclass
class CallSDP:
    caller_sdp: Optional[SDPMediaDesc] = None  # from INVITE
    callee_sdp: Optional[SDPMediaDesc] = None  # from 200 OK


def extract_sdp(sip_packets) -> CallSDP:
    desc = CallSDP()
    for pkt in sip_packets:
        raw = pkt.raw_message or ""
        if not raw:
            continue
        if pkt.method == "INVITE" and desc.caller_sdp is None:
            sdp = parse_sdp(raw)
            if sdp:
                desc.caller_sdp = sdp
        elif pkt.response_code == 200 and desc.callee_sdp is None:
            sdp = parse_sdp(raw)
            if sdp:
                desc.callee_sdp = sdp
    return desc


def correlate(rtp_packets: list[RTPPacket], sdp: CallSDP) -> tuple[list, list]:
    """
    Split the global RTP packet list into two directional streams for this call.
    Returns (caller_to_callee, callee_to_caller).
    """
    caller_ip   = sdp.caller_sdp.ip   if sdp.caller_sdp else None
    caller_port = sdp.caller_sdp.port if sdp.caller_sdp else None
    callee_ip   = sdp.callee_sdp.ip   if sdp.callee_sdp else None
    callee_port = sdp.callee_sdp.port if sdp.callee_sdp else None

    a2b, b2a = [], []
    for pkt in rtp_packets:
        if caller_ip and caller_port and pkt.source_ip == caller_ip and pkt.source_port == caller_port:
            a2b.append(pkt)
        elif callee_ip and callee_port and pkt.source_ip == callee_ip and pkt.source_port == callee_port:
            b2a.append(pkt)
    return a2b, b2a


# ── Top-level entry point ─────────────────────────────────────────────────

def analyze_rtp(
    file_path: str,
    sessions: list,
    sip_packet_map: dict,
) -> dict[str, list[RTPStreamMetrics]]:
    """
    Full pipeline: extract RTP → correlate to calls via SDP → compute metrics.
    Returns {call_id: [RTPStreamMetrics, ...]} for answered calls only.
    """
    answered = [s for s in sessions if s.status == "ANSWERED"]
    if not answered:
        return {}

    rtp_packets = extract_rtp_packets(file_path)
    if not rtp_packets:
        logger.info("No RTP packets found")
        return {}

    logger.info(f"Extracted {len(rtp_packets)} RTP packets for {len(answered)} answered call(s)")
    results: dict[str, list[RTPStreamMetrics]] = []
    results = {}

    for session in answered:
        sip_pkts = sip_packet_map.get(session.call_id, [])
        sdp = extract_sdp(sip_pkts)
        if not sdp.caller_sdp and not sdp.callee_sdp:
            continue

        a2b, b2a = correlate(rtp_packets, sdp)
        ptime = (sdp.caller_sdp or sdp.callee_sdp).ptime_ms

        call_metrics: list[RTPStreamMetrics] = []
        has_a2b = len(a2b) > 0
        has_b2a = len(b2a) > 0

        for direction_pkts, has_other in [(a2b, has_b2a), (b2a, has_a2b)]:
            if not direction_pkts:
                continue
            try:
                m = _compute_metrics(direction_pkts, ptime_ms=ptime)
                m.is_one_way = not has_other
                call_metrics.append(m)
            except Exception as e:
                logger.warning(f"Metrics error for {session.call_id}: {e}")

        if call_metrics:
            results[session.call_id] = call_metrics

    return results
