"""RFC 6238 TOTP (time-based one-time passwords), standard-library only.

Used for optional two-factor authentication. No third-party dependency: TOTP is
a short HMAC-SHA1 construction over a time counter, so it is cheaper to implement
correctly than to pull in a library. Compatible with Google Authenticator, Authy,
1Password, etc. via the standard ``otpauth://`` provisioning URI.
"""

from __future__ import annotations

import base64
import hmac
import os
import struct
import time
import urllib.parse
from hashlib import sha1

DIGITS = 6
PERIOD = 30


def generate_secret(num_bytes: int = 20) -> str:
    """Return a new base32 secret (no padding), suitable for authenticator apps."""
    return base64.b32encode(os.urandom(num_bytes)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = DIGITS) -> str:
    padding = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + padding)
    digest = hmac.new(key, struct.pack(">Q", counter), sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str, *, at: float | None = None, period: int = PERIOD, digits: int = DIGITS) -> str:
    """Return the current TOTP code for a secret."""
    now = at if at is not None else time.time()
    return _hotp(secret_b32, int(now // period), digits)


def verify(
    secret_b32: str,
    code: str,
    *,
    window: int = 1,
    period: int = PERIOD,
    digits: int = DIGITS,
    at: float | None = None,
) -> bool:
    """Verify a code against a secret, tolerating +/- ``window`` time steps."""
    if not secret_b32 or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    code = code.zfill(digits)
    now = at if at is not None else time.time()
    counter = int(now // period)
    for step in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + step, digits), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account_name: str, *, issuer: str = "ATIS") -> str:
    """Return the otpauth:// URI to enrol the secret in an authenticator app."""
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode(
        {
            "secret": secret_b32,
            "issuer": issuer,
            "digits": DIGITS,
            "period": PERIOD,
            "algorithm": "SHA1",
        }
    )
    return f"otpauth://totp/{label}?{params}"
