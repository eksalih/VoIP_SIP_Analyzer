"""
Password hashing and signed session tokens (v2.3.0), standard library only.

  * Passwords: scrypt with a random per-user salt, compared in constant time.
  * Tokens: base64url(JSON payload) + "." + HMAC-SHA256 signature, with an expiry.
  * The signing secret comes from AUTH_SECRET; if unset, one is generated once
    and stored in the data directory so sessions survive restarts.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)

_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
TOKEN_TTL_SECONDS = 12 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def _secret() -> bytes:
    env = os.getenv("AUTH_SECRET")
    if env:
        return env.encode()
    path = os.path.join(os.getenv("DATA_DIR", "./data"), ".auth_secret")
    try:
        with open(path, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32).encode()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
    except OSError as e:
        logger.warning(f"Could not persist auth secret ({e}); sessions will reset on restart")
    return key


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user_id: int, ttl: int = TOKEN_TTL_SECONDS, now: Optional[float] = None) -> str:
    payload = _b64(json.dumps({"sub": user_id, "exp": int((now or time.time()) + ttl)}).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str, now: Optional[float] = None) -> Optional[int]:
    """Return the user id for a valid, unexpired token, else None."""
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if data["exp"] < (now or time.time()):
            return None
        return int(data["sub"])
    except (ValueError, KeyError, TypeError):
        return None
