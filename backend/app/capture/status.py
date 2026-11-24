"""
Capture status hand-off (v2.3.0).

The capture service runs in its own container, so it reports health to the
backend through a small JSON file in the shared data folder. It is written
atomically (temp file + rename) so the backend never reads a half-written file,
and the backend treats a file that has stopped updating as "not running".
"""
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 5.0
STALE_AFTER_SECONDS = 20.0


def status_path() -> str:
    return os.getenv("CAPTURE_STATUS_FILE") or os.path.join(os.getenv("DATA_DIR", "./data"), "capture_status.json")


def write_status(data: dict, path: Optional[str] = None) -> None:
    """Best-effort: a status failure must never disturb capture."""
    path = path or status_path()
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({**data, "updated_at": time.time()}, f)
        os.replace(tmp, path)
    except OSError as e:
        logger.debug(f"Could not write capture status: {e}")


def read_status(path: Optional[str] = None, now: Optional[float] = None) -> dict:
    """
    state: "not_configured" (no file ever written), "running", "stopped"
    (clean shutdown) or "stale" (the service died or hung: no heartbeat).
    """
    path = path or status_path()
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"state": "not_configured"}
    except (OSError, ValueError):
        return {"state": "stale", "detail": "status file unreadable"}

    age = (now or time.time()) - float(data.get("updated_at", 0))
    if data.get("running") and age > STALE_AFTER_SECONDS:
        state = "stale"
    else:
        state = "running" if data.get("running") else "stopped"
    return {**data, "state": state, "age_seconds": round(age, 1)}
