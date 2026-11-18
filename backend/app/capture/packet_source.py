"""
Packet sources for the live capture service (v2.3.0).

A PacketSource yields CapturedPacket records. Two implementations share the
interface so everything downstream (call tracker, RTP spooler) can be tested
with no network at all:

  * PcapReplaySource     - streams packets from a PCAP/PCAPNG file
  * LiveInterfaceSource  - sniffs a network interface (e.g. a SPAN/mirror port)

Only UDP and TCP payloads are yielded. VLAN tags are transparent: Scapy stacks
the layers, so the IP/UDP/TCP layers are found regardless of 802.1Q headers.
"""
import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapturedPacket:
    timestamp: float          # capture time, epoch seconds
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str             # "udp" or "tcp"
    payload: bytes


def to_captured_packet(pkt) -> Optional[CapturedPacket]:
    """Convert a Scapy packet to a CapturedPacket; None if it is not UDP/TCP with a payload."""
    from scapy.all import IP, IPv6, UDP, TCP

    if pkt.haslayer(IP):
        ip = pkt[IP]
    elif pkt.haslayer(IPv6):
        ip = pkt[IPv6]
    else:
        return None

    if pkt.haslayer(UDP):
        layer, proto = pkt[UDP], "udp"
    elif pkt.haslayer(TCP):
        layer, proto = pkt[TCP], "tcp"
    else:
        return None

    payload = bytes(layer.payload)
    if not payload:
        return None

    return CapturedPacket(
        timestamp=float(pkt.time),
        src_ip=ip.src,
        dst_ip=ip.dst,
        src_port=int(layer.sport),
        dst_port=int(layer.dport),
        protocol=proto,
        payload=payload,
    )


class PacketSource(ABC):
    """Iterable of CapturedPacket. Iteration ends when the source is exhausted or stopped."""

    @abstractmethod
    def __iter__(self) -> Iterator[CapturedPacket]:
        ...

    @abstractmethod
    def stop(self) -> None:
        """Ask the source to finish; safe to call from another thread, and more than once."""


class PcapReplaySource(PacketSource):
    """
    Replays a capture file as a stream (never loads the whole file).

    speed=None   -> as fast as possible (tests, offline processing)
    speed=1.0    -> original timing; 2.0 twice as fast, 0.5 half speed
    """

    def __init__(self, path: str, speed: Optional[float] = None):
        self.path = path
        self.speed = speed
        self._stopped = threading.Event()

    def __iter__(self) -> Iterator[CapturedPacket]:
        from scapy.utils import PcapReader

        first_ts: Optional[float] = None
        start_wall = time.monotonic()

        with PcapReader(self.path) as reader:
            for pkt in reader:
                if self._stopped.is_set():
                    return
                cp = to_captured_packet(pkt)
                if cp is None:
                    continue
                if self.speed:
                    if first_ts is None:
                        first_ts = cp.timestamp
                    due = (cp.timestamp - first_ts) / self.speed
                    delay = due - (time.monotonic() - start_wall)
                    if delay > 0:
                        # wake early if stopped during a long gap
                        if self._stopped.wait(delay):
                            return
                yield cp

    def stop(self) -> None:
        self._stopped.set()


class LiveInterfaceSource(PacketSource):
    """
    Sniffs a network interface with Scapy (needs NET_RAW / root).

    Packets are handed from the sniffing thread to the consumer through a
    bounded queue. If the consumer falls behind, new packets are dropped and
    counted in `dropped` rather than growing memory without limit.
    """

    def __init__(self, interface: str, bpf_filter: Optional[str] = None, queue_size: int = 50_000):
        self.interface = interface
        self.bpf_filter = bpf_filter
        self._queue: "queue.Queue[CapturedPacket]" = queue.Queue(maxsize=queue_size)
        self._stopped = threading.Event()
        self._sniffer = None
        self.dropped = 0
        self.captured = 0

    def _on_packet(self, pkt) -> None:
        cp = to_captured_packet(pkt)
        if cp is None:
            return
        try:
            self._queue.put_nowait(cp)
            self.captured += 1
        except queue.Full:
            self.dropped += 1

    def __iter__(self) -> Iterator[CapturedPacket]:
        from scapy.all import AsyncSniffer

        self._sniffer = AsyncSniffer(
            iface=self.interface,
            filter=self.bpf_filter,
            prn=self._on_packet,
            store=False,
        )
        self._sniffer.start()
        logger.info(f"Live capture started on {self.interface} (filter={self.bpf_filter!r})")
        try:
            while not self._stopped.is_set():
                try:
                    yield self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
            # Drain what was already captured before stopping
            while True:
                try:
                    yield self._queue.get_nowait()
                except queue.Empty:
                    break
        finally:
            self._halt_sniffer()

    def _halt_sniffer(self) -> None:
        sniffer, self._sniffer = self._sniffer, None
        if sniffer is not None:
            try:
                sniffer.stop()
            except Exception as e:  # sniffer may already be stopped
                logger.debug(f"Sniffer stop: {e}")
        if self.dropped:
            logger.warning(f"Live capture dropped {self.dropped} packets (consumer too slow)")

    def stop(self) -> None:
        self._stopped.set()
