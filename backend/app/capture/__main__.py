"""
Entry point for the live capture service:  python -m app.capture

Needs raw-socket access (root or CAP_NET_RAW) and an interface that receives
mirrored SIP/RTP traffic (a SPAN / port-mirror destination).
"""
import asyncio
import logging
import signal
import sys

from app.capture.live_store import LiveCallStore
from app.capture.packet_source import LiveInterfaceSource
from app.capture.service import CaptureService, CaptureSettings
from app.db.database import AsyncSessionLocal, init_db

logger = logging.getLogger("app.capture")

RECORDING_NOTICE = (
    "Call recording is ENABLED. Recording telephone calls may require notice to or consent "
    "from the parties under the laws of your jurisdiction. You are responsible for compliance. "
    "Set LIVE_RECORDING_ENABLED=false to keep call records and quality metrics without audio."
)


async def amain(settings: CaptureSettings) -> int:
    await init_db()
    if settings.record_audio:
        logger.warning(RECORDING_NOTICE)

    source = LiveInterfaceSource(settings.interface, settings.bpf_filter)
    service = CaptureService(
        source, LiveCallStore(AsyncSessionLocal, record_audio=settings.record_audio), settings, live=True
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, service.stop)
        except NotImplementedError:  # non-POSIX platforms
            pass

    logger.info(f"Capturing on {settings.interface} (filter: {settings.bpf_filter})")
    try:
        await service.run()
    except PermissionError:
        logger.error("Permission denied opening the interface: run as root or grant NET_RAW.")
        return 1
    except OSError as e:
        logger.error(f"Cannot capture on '{settings.interface}': {e}")
        return 1
    logger.info(
        f"Capture stopped: {service.stats['packets']} packets, "
        f"{service.stats['calls_finalized']} calls saved, {service.stats['errors']} errors, "
        f"{source.dropped} packets dropped"
    )
    return 0


def list_interfaces() -> None:
    from scapy.all import get_if_list

    print("Network interfaces (set CAPTURE_INTERFACE to the one connected to the mirror/SPAN port):")
    for name in get_if_list():
        print(f"  {name}")


def main() -> None:
    if "--list-interfaces" in sys.argv[1:]:
        list_interfaces()
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(asyncio.run(amain(CaptureSettings.from_env())))


if __name__ == "__main__":
    main()
