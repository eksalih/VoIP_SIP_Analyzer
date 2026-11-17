"""
Audio storage helpers for reconstructed call recordings (v2.2.0).

All access to WAV files on disk goes through here so that paths are always
resolved inside the recordings directory and cleanup is best-effort.
"""
import logging
import os
from typing import Iterable, Optional

from app.services.pcap_service import recordings_dir

logger = logging.getLogger(__name__)


def resolve_audio_path(rel_name: Optional[str]) -> Optional[str]:
    """Absolute path for a stored recording, or None if unsafe/missing."""
    if not rel_name:
        return None
    base = os.path.realpath(recordings_dir())
    full = os.path.realpath(os.path.join(base, rel_name))
    if os.path.commonpath([base, full]) != base:
        logger.warning(f"Refusing audio path outside recordings dir: {rel_name!r}")
        return None
    return full if os.path.isfile(full) else None


def remove_audio_files(rel_names: Iterable[Optional[str]]) -> int:
    """Delete the given recordings; returns how many files were removed."""
    removed = 0
    for name in rel_names:
        path = resolve_audio_path(name)
        if not path:
            continue
        try:
            os.unlink(path)
            removed += 1
        except OSError as e:
            logger.warning(f"Could not delete recording {name}: {e}")
    return removed


def remove_all_audio() -> int:
    """Delete every call_*.wav in the recordings directory (used by Clear All)."""
    base = recordings_dir()
    if not os.path.isdir(base):
        return 0
    names = [n for n in os.listdir(base) if n.startswith("call_") and n.endswith(".wav")]
    return remove_audio_files(names)
