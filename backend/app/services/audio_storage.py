"""
Audio storage helpers for reconstructed call recordings (v2.2.0).

All access to WAV files on disk goes through here so that paths are always
resolved inside the recordings directory and cleanup is best-effort.
"""
import logging
import os
from typing import Iterable, Optional

from fastapi.responses import Response, StreamingResponse

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


def build_audio_response(path: str, filename: str, range_header: Optional[str], download: bool):
    """
    Serve a WAV with HTTP Range support (needed for seeking in browser players;
    the installed Starlette's FileResponse does not honour Range) and an inline
    disposition unless a download is requested.
    """
    size = os.path.getsize(path)
    start, end, status = 0, size - 1, 200

    if range_header and range_header.startswith("bytes="):
        spec = range_header[6:].split(",")[0].strip()
        first, _, last = spec.partition("-")
        try:
            if first == "":                      # suffix range: last N bytes
                start = max(0, size - int(last))
            else:
                start = int(first)
                end = int(last) if last else size - 1
        except ValueError:
            start, end = 0, size - 1             # malformed -> ignore, serve whole file
        else:
            end = min(end, size - 1)
            if start > end or start >= size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            status = 206

    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{filename}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def _chunks(chunk_size: int = 64 * 1024):
        remaining = length
        with open(path, "rb") as f:
            f.seek(start)
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(_chunks(), status_code=status, media_type="audio/wav", headers=headers)


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
