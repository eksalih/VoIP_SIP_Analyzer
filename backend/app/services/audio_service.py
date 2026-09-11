"""
Audio Reconstruction Service
Extracts RTP payloads from PCAP files and reconstructs WAV audio.

Supports:
- PCMU (G.711 µ-law) — payload type 0
- PCMA (G.711 A-law) — payload type 8

No external codec dependencies — uses Python's audioop stdlib for decoding.
"""

import audioop
import logging
import struct
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Codec to payload type mapping
CODEC_PT_MAP = {
    0: "PCMU",    # G.711 µ-law
    8: "PCMA",    # G.711 A-law
}

# Reverse mapping
PT_CODEC_MAP = {v: k for k, v in CODEC_PT_MAP.items()}

# RTP payload size for each codec at 20ms ptime (typical)
EXPECTED_BYTES_20MS = {
    "PCMU": 160,  # 8000 Hz * 0.02s = 160 samples = 160 bytes (µ-law is 1 byte/sample)
    "PCMA": 160,  # Same as PCMU
}


@dataclass
class RTPPayload:
    """Single RTP packet's audio data"""
    timestamp_epoch: float
    sequence: int
    rtp_timestamp: int
    payload_type: int
    codec: str
    payload: bytes
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int


@dataclass
class RTPDirection:
    """Directional RTP stream (one endpoint pair)"""
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    payloads: list[RTPPayload] = field(default_factory=list)
    ssrc: Optional[str] = None
    codec: Optional[str] = None

    def key(self) -> tuple:
        """Unique identifier for this direction"""
        return (self.source_ip, self.source_port, self.destination_ip, self.destination_port)


def extract_rtp_payloads_from_pcap(
    file_path: str,
    call_ids: Optional[set[str]] = None,
) -> dict[str, list[RTPPayload]]:
    """
    Extract RTP payloads from PCAP file, grouped by SIP Call-ID.

    Args:
        file_path: Path to PCAP/PCAPNG file
        call_ids: If provided, only extract packets for these Call-IDs

    Returns:
        Dict mapping Call-ID → list of RTPPayload objects
    """
    try:
        from scapy.all import rdpcap, UDP, IP, Raw
    except ImportError:
        logger.error("Scapy not available for RTP extraction")
        return {}

    results: dict[str, list[RTPPayload]] = {}

    try:
        packets_by_call = _group_packets_by_call_id(file_path, call_ids)

        for call_id, call_packets in packets_by_call.items():
            rtp_payloads = []

            for pkt in call_packets:
                if not (pkt.haslayer(UDP) and pkt.haslayer(IP) and pkt.haslayer(Raw)):
                    continue

                payload = pkt[Raw].load
                if len(payload) < 12:
                    continue

                # Parse RTP header
                rtp_hdr = _parse_rtp_header(payload)
                if rtp_hdr is None:
                    continue

                version, pt, seq, ts, ssrc = rtp_hdr

                # Only extract known audio codecs
                if pt not in CODEC_PT_MAP:
                    continue

                codec = CODEC_PT_MAP[pt]

                # RTP payload is everything after the 12-byte header (+ CSRC list if present)
                cc = (payload[0] & 0x0F)  # CSRC count
                csrc_bytes = cc * 4
                rtp_payload_start = 12 + csrc_bytes

                if len(payload) <= rtp_payload_start:
                    continue

                audio_data = payload[rtp_payload_start:]

                rtp_payloads.append(RTPPayload(
                    timestamp_epoch=float(pkt.time),
                    sequence=seq,
                    rtp_timestamp=ts,
                    payload_type=pt,
                    codec=codec,
                    payload=audio_data,
                    source_ip=pkt[IP].src,
                    source_port=pkt[UDP].sport,
                    destination_ip=pkt[IP].dst,
                    destination_port=pkt[UDP].dport,
                ))

            if rtp_payloads:
                results[call_id] = rtp_payloads

    except Exception as e:
        logger.error(f"RTP payload extraction error: {e}")

    return results


def _group_packets_by_call_id(file_path: str, call_ids: Optional[set[str]] = None):
    """Group PCAP packets by SIP Call-ID for later processing"""
    from scapy.all import rdpcap, UDP, IP, Raw
    from app.core.sip_parser import CALL_ID_RE

    grouped = {}

    try:
        for pkt in rdpcap(file_path):
            if not (pkt.haslayer(UDP) and pkt.haslayer(IP) and pkt.haslayer(Raw)):
                continue

            payload = pkt[Raw].load

            # Try to extract Call-ID if this is SIP
            try:
                payload_str = payload.decode("utf-8", errors="ignore")
                call_id_match = CALL_ID_RE.search(payload_str)
                if call_id_match:
                    call_id = call_id_match.group(1).strip()

                    # Filter by call_ids if provided
                    if call_ids and call_id not in call_ids:
                        continue

                    if call_id not in grouped:
                        grouped[call_id] = []
                    grouped[call_id].append(pkt)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error grouping packets by Call-ID: {e}")

    return grouped


def _parse_rtp_header(payload: bytes) -> Optional[tuple]:
    """
    Parse RTP v2 header.

    Returns:
        (version, payload_type, sequence, timestamp, ssrc) or None if invalid
    """
    if len(payload) < 12:
        return None

    version = (payload[0] >> 6) & 0x03
    if version != 2:
        return None

    pt = payload[1] & 0x7F
    seq = struct.unpack(">H", payload[2:4])[0]
    ts = struct.unpack(">I", payload[4:8])[0]
    ssrc = struct.unpack(">I", payload[8:12])[0]

    return (version, pt, seq, ts, ssrc)


def reconstruct_audio(
    payloads: list[RTPPayload],
    output_dir: Path,
    call_id: str,
    direction_label: str = "unknown",
    full_direction: str = "unknown",
) -> Optional[dict]:
    """
    Reconstruct WAV file from RTP audio payloads.

    Args:
        payloads: List of RTPPayload objects (must be same direction, codec)
        output_dir: Directory to write WAV file
        call_id: Call ID for file naming
        direction_label: "inbound", "outbound", or custom label for filename

    Returns:
        Dict with reconstruction details, or None if failed
    """
    if not payloads:
        return None

    # Ensure all payloads use the same codec
    codecs = {p.codec for p in payloads}
    if len(codecs) > 1:
        logger.warning(f"Mixed codecs in direction {direction_label}: {codecs}")
        return None

    codec = payloads[0].codec
    if codec not in ["PCMU", "PCMA"]:
        logger.warning(f"Unsupported codec {codec}")
        return None

    # Sort by RTP timestamp to ensure correct playback order
    payloads_sorted = sorted(payloads, key=lambda p: p.rtp_timestamp)

    # Decode audio
    try:
        audio_bytes = bytearray()
        packets_used = 0
        packets_missing = 0

        prev_ts = None
        for p in payloads_sorted:
            # Detect packet loss (sequence gap or timestamp jump)
            if prev_ts is not None:
                expected_ts_delta = 160  # Typical for 20ms frames at 8kHz
                ts_delta = (p.rtp_timestamp - prev_ts) & 0xFFFFFFFF
                if ts_delta > expected_ts_delta + 100:  # Allow some jitter
                    gap_frames = (ts_delta // expected_ts_delta) - 1
                    packets_missing += gap_frames
                    logger.debug(f"Detected {gap_frames} missing packets in {direction_label}")

            # Decode payload
            if codec == "PCMU":
                # G.711 µ-law → linear PCM
                linear_pcm = audioop.ulaw2lin(p.payload, 1)
            elif codec == "PCMA":
                # G.711 A-law → linear PCM
                linear_pcm = audioop.alaw2lin(p.payload, 1)
            else:
                continue

            audio_bytes.extend(linear_pcm)
            packets_used += 1
            prev_ts = p.rtp_timestamp

        if not audio_bytes:
            logger.warning(f"No audio data decoded for {direction_label}")
            return None

        # Write WAV file
        filename = f"{call_id}_{direction_label}_{codec}.wav"
        output_path = output_dir / filename

        output_dir.mkdir(parents=True, exist_ok=True)

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(8000)  # 8kHz (standard VoIP)
            wav_file.writeframes(bytes(audio_bytes))

        duration_seconds = len(audio_bytes) / (2 * 8000)  # 2 bytes per sample, 8kHz

        return {
            "call_id": call_id,
            "direction": full_direction,
            "codec": codec,
            "file_path": str(output_path.relative_to(output_path.parent.parent)),
            "file_size_bytes": output_path.stat().st_size,
            "duration_seconds": duration_seconds,
            "packets_used": packets_used,
            "packets_missing": packets_missing,
            "status": "SUCCESS" if packets_missing == 0 else "PARTIAL",
            "notes": None,
        }

    except Exception as e:
        logger.error(f"Audio reconstruction failed for {direction_label}: {e}")
        return {
            "direction": direction_label,
            "status": "FAILED",
            "notes": str(e),
        }


def reconstruct_call_audio(
    file_path: str,
    call_id: str,
    output_dir: Path,
) -> list[dict]:
    """
    Reconstruct all available audio directions for a call.

    Args:
        file_path: Path to PCAP file
        call_id: SIP Call-ID
        output_dir: Directory to write WAV files

    Returns:
        List of reconstruction result dicts (one per direction)
    """
    # Extract RTP payloads for this call
    payloads_by_call = extract_rtp_payloads_from_pcap(file_path, {call_id})

    if call_id not in payloads_by_call or not payloads_by_call[call_id]:
        logger.info(f"No RTP packets found for call {call_id}")
        return []

    payloads = payloads_by_call[call_id]

    # Group by direction (source + destination endpoint pair)
    directions: dict[tuple, RTPDirection] = {}

    for p in payloads:
        direction = RTPDirection(
            source_ip=p.source_ip,
            source_port=p.source_port,
            destination_ip=p.destination_ip,
            destination_port=p.destination_port,
            codec=p.codec,
        )

        key = direction.key()
        if key not in directions:
            directions[key] = direction

        directions[key].payloads.append(p)

    # Reconstruct audio for each direction
    results = []
    for idx, direction in enumerate(directions.values()):
        if direction.payloads:
            # Create a simple numeric label for filename: "inbound", "outbound", etc.
            if idx == 0:
                direction_label = "inbound"
            elif idx == 1:
                direction_label = "outbound"
            else:
                direction_label = f"stream_{idx}"

            full_direction = f"{direction.source_ip}:{direction.source_port} → {direction.destination_ip}:{direction.destination_port}"

            result = reconstruct_audio(
                payloads=direction.payloads,
                output_dir=output_dir,
                call_id=call_id,
                direction_label=direction_label,
                full_direction=full_direction,
            )

            if result:
                results.append(result)

    return results
