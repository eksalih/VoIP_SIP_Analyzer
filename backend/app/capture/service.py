"""
Live capture service (v2.3.0).

Wires a PacketSource to the tracker, the RTP spooler and the database store:

    packets -> LiveCallTracker -> LiveCallStore (IN_PROGRESS updates, final save)
            -> RTPSpooler      -> recording + quality metrics at call end

Works with any PacketSource, so tests replay a PCAP and production sniffs the
mirror port. In live mode (`live=True`) a timer advances the tracker with the
wall clock so calls finish even when the network goes quiet; when replaying a
file the packet timestamps are the only clock.
"""
import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from app.capture.call_tracker import LiveCallTracker, TrackerEvent
from app.capture.live_store import LiveCallStore
from app.capture.packet_source import PacketSource
from app.capture.rtp_spool import RTPSpooler
from app.core.rtp_analyzer import extract_sdp

logger = logging.getLogger(__name__)

_END = object()


@dataclass
class CaptureSettings:
    interface: str = "eth1"
    bpf_filter: str = "udp or tcp port 5060"
    spool_dir: str = "./data/spool"
    record_audio: bool = True
    settle_seconds: float = 30.0
    idle_timeout: float = 60.0
    media_idle_timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "CaptureSettings":
        def flag(name, default):
            return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

        return cls(
            interface=os.getenv("CAPTURE_INTERFACE", cls.interface),
            # UDP is kept wide open (not just 5060) because RTP uses dynamic ports
            bpf_filter=os.getenv("CAPTURE_FILTER", cls.bpf_filter),
            spool_dir=os.getenv("CAPTURE_SPOOL_DIR", cls.spool_dir),
            record_audio=flag("LIVE_RECORDING_ENABLED", True),
            settle_seconds=float(os.getenv("CAPTURE_SETTLE_SECONDS", cls.settle_seconds)),
            idle_timeout=float(os.getenv("CAPTURE_IDLE_TIMEOUT", cls.idle_timeout)),
            media_idle_timeout=float(os.getenv("CAPTURE_MEDIA_IDLE_TIMEOUT", cls.media_idle_timeout)),
        )


class CaptureService:
    def __init__(self, source: PacketSource, store: LiveCallStore, settings: Optional[CaptureSettings] = None,
                 live: bool = True, tick_seconds: float = 1.0):
        self.source = source
        self.store = store
        self.settings = settings or CaptureSettings()
        self.live = live
        self.tick_seconds = tick_seconds
        self.tracker = LiveCallTracker(
            settle_seconds=self.settings.settle_seconds,
            idle_timeout=self.settings.idle_timeout,
            media_idle_timeout=self.settings.media_idle_timeout,
        )
        self.spooler = RTPSpooler(self.settings.spool_dir)
        self.run_id: Optional[int] = None
        self.stats = {"packets": 0, "calls_finalized": 0, "errors": 0}
        self._lock = asyncio.Lock()   # keeps packet handling and the timer from interleaving DB writes
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        stopper = getattr(self.source, "stop", None)
        if callable(stopper):
            stopper()

    async def run(self) -> None:
        await self.store.recover_orphans()
        self.run_id = await self.store.start_run()
        ticker = asyncio.create_task(self._tick_loop()) if self.live else None
        iterator = iter(self.source)
        try:
            while not self._stop:
                cp = await asyncio.to_thread(next, iterator, _END)
                if cp is _END:
                    break
                async with self._lock:
                    self.stats["packets"] += 1
                    await self._handle_all(self.tracker.feed(cp))
                    call_id = self.spooler.feed(cp)
                    if call_id:
                        self.tracker.note_media(call_id, cp.timestamp)
        finally:
            if ticker:
                ticker.cancel()
            async with self._lock:
                await self._handle_all(self.tracker.flush())
                self.spooler.close_all()
                await self.store.end_run(self.run_id)

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            async with self._lock:
                await self._handle_all(self.tracker.advance(time.time()))

    async def _handle_all(self, events: list[TrackerEvent]) -> None:
        for ev in events:
            try:
                await self._handle(ev)
            except Exception:
                # One bad call must never stop the capture
                self.stats["errors"] += 1
                logger.exception(f"Failed to store call {ev.session.call_id}")

    async def _handle(self, ev: TrackerEvent) -> None:
        call_id = ev.session.call_id
        if ev.kind == "updated":
            self.spooler.update_sdp(call_id, extract_sdp(ev.session.packets))
            await self.store.update(self.run_id, ev.session)
            return
        data = self.spooler.load(call_id)
        try:
            await self.store.finalize(self.run_id, ev.session, data)
            self.stats["calls_finalized"] += 1
        finally:
            self.spooler.close_call(call_id)
