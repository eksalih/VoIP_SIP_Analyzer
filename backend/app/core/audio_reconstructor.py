"""
Audio Reconstructor
Rebuilds call audio from RTP payloads captured in a PCAP and writes a stereo
16-bit WAV (caller = left channel, callee = right channel).

Supported codecs: G.711 u-law (PT 0) and A-law (PT 8), 8 kHz.
Other codecs (G.722, G.729, Opus ...) are reported as unsupported, never fatal.

Timing: each packet is placed by its RTP timestamp relative to the first packet
of the call, so silence/lost packets keep the original timeline.
"""
import array
import logging
import wave
from dataclasses import dataclass
from typing import Optional

from app.core.rtp_analyzer import RTPPacket

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
SUPPORTED_PTS = {0: "PCMU", 8: "PCMA"}


# ── G.711 decode tables (ITU-T G.711, pure Python) ────────────────────────

def _ulaw_to_pcm(byte: int) -> int:
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = (((mantissa << 3) + 0x84) << exponent) - 0x84
    return -sample if sign else sample


def _alaw_to_pcm(byte: int) -> int:
    byte ^= 0x55
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    if exponent == 0:
        sample = (mantissa << 4) + 8
    else:
        sample = ((mantissa << 4) + 0x108) << (exponent - 1)
    return sample if sign else -sample


_ULAW_TABLE = [_ulaw_to_pcm(i) for i in range(256)]
_ALAW_TABLE = [_alaw_to_pcm(i) for i in range(256)]


def decode_g711(payload: bytes, payload_type: int) -> list[int]:
    table = _ULAW_TABLE if payload_type == 0 else _ALAW_TABLE
    return [table[b] for b in payload]


# ── Channel building ──────────────────────────────────────────────────────

def _build_channel(packets: list[RTPPacket], origin_ts: int, total_samples: int) -> array.array:
    """Place decoded packets on a silent timeline using RTP timestamps."""
    channel = array.array("h", bytes(2 * total_samples))
    for pkt in sorted(packets, key=lambda p: p.timestamp_epoch):
        if pkt.payload_type not in SUPPORTED_PTS or not pkt.payload:
            continue
        offset = (pkt.rtp_timestamp - origin_ts) % (2 ** 32)
        if offset > total_samples:  # wrapped/earlier than origin -> ignore
            continue
        samples = decode_g711(pkt.payload, pkt.payload_type)
        end = min(offset + len(samples), total_samples)
        channel[offset:end] = array.array("h", samples[: end - offset])
    return channel


@dataclass
class AudioResult:
    path: str
    duration_seconds: float
    codec: str
    channels: int  # 1 = one direction only, 2 = both


class UnsupportedCodecError(ValueError):
    pass


def reconstruct_audio(
    a2b: list[RTPPacket],
    b2a: list[RTPPacket],
    out_path: str,
) -> Optional[AudioResult]:
    """
    Write a WAV for one call. a2b/b2a are the directional packet lists from
    rtp_analyzer.correlate (extracted with keep_payload=True).
    Returns None when neither direction has packets; raises UnsupportedCodecError
    when the codec is not G.711.
    """
    directions = [d for d in (a2b, b2a) if d]
    if not directions:
        return None

    pts = {d[0].payload_type for d in directions}
    if not pts <= set(SUPPORTED_PTS):
        raise UnsupportedCodecError(f"Unsupported payload type(s): {sorted(pts - set(SUPPORTED_PTS))}")

    # Common timeline origin = earliest packet (by capture time) across both directions
    first = min((min(d, key=lambda p: p.timestamp_epoch) for d in directions),
                key=lambda p: p.timestamp_epoch)
    start_epoch = first.timestamp_epoch

    def _start_sample(d: list[RTPPacket]) -> int:
        p = min(d, key=lambda x: x.timestamp_epoch)
        return int(round((p.timestamp_epoch - start_epoch) * SAMPLE_RATE))

    def _stream_len(d: list[RTPPacket]) -> int:
        p0 = min(d, key=lambda x: x.timestamp_epoch)
        last = max(d, key=lambda x: x.timestamp_epoch)
        return ((last.rtp_timestamp - p0.rtp_timestamp) % (2 ** 32)) + len(last.payload)

    # Build each direction on its own timeline, then shift by its start offset
    built: list[tuple[int, array.array]] = []
    for d in (a2b, b2a):
        if not d:
            built.append((0, array.array("h")))
            continue
        origin = min(d, key=lambda x: x.timestamp_epoch).rtp_timestamp
        built.append((_start_sample(d), _build_channel(d, origin, _stream_len(d))))

    total = max((off + len(ch) for off, ch in built), default=0)
    if total == 0:
        return None

    two_ch = bool(a2b) and bool(b2a)
    frames = array.array("h", bytes(2 * total * (2 if two_ch else 1)))
    if two_ch:
        for idx, (off, ch) in enumerate(built):
            frames[(off * 2 + idx):((off + len(ch)) * 2):2] = ch
    else:
        off, ch = built[0] if a2b else built[1]
        frames[off:off + len(ch)] = ch

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(2 if two_ch else 1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(frames.tobytes() if _is_little_endian() else _swap(frames))

    return AudioResult(
        path=out_path,
        duration_seconds=round(total / SAMPLE_RATE, 2),
        codec=SUPPORTED_PTS[next(iter(pts))],
        channels=2 if two_ch else 1,
    )


def _is_little_endian() -> bool:
    import sys
    return sys.byteorder == "little"


def _swap(frames: array.array) -> bytes:
    frames.byteswap()
    return frames.tobytes()
