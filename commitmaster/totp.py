"""RFC 6238 TOTP (SHA-1, 6 digits, 30 second step).

The standard library is enough for a real authenticator code. This module
does not contain a secret. The server reads the secret from its own
environment or from a file next to the server database.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def normalize_secret(secret: str) -> bytes:
    text = "".join(secret.split()).upper()
    pad = "=" * ((8 - len(text) % 8) % 8)
    return base64.b32decode(text + pad, casefold=True)


def totp_at(secret: str, when: float | None = None, step: int = 30, digits: int = 6) -> str:
    counter = int((time.time() if when is None else when) // step)
    key = normalize_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """Accept the current code and one step on either side. No universal bypass."""
    given = "".join(str(code or "").split())
    if len(given) != 6 or not given.isdigit() or not secret:
        return False
    now = time.time()
    for delta in range(-window, window + 1):
        if hmac.compare_digest(totp_at(secret, now + delta * 30), given):
            return True
    return False
