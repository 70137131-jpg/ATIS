"""Single-use MFA recovery (backup) codes.

Recovery codes let a user who has lost their authenticator still sign in. They
are generated once, shown to the user once, and only their hashes are stored
(same Werkzeug hashing as passwords). Each code is consumed on use, so it cannot
be replayed.
"""

from __future__ import annotations

import json
import secrets
import string

from werkzeug.security import check_password_hash, generate_password_hash

CODE_COUNT = 10
GROUP_LEN = 4
GROUPS = 2  # -> "abcd-efgh"
# Unambiguous alphabet (no 0/O/1/I/l) so hand-typed codes are less error-prone.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_codes(count: int = CODE_COUNT) -> list[str]:
    """Return a list of new plaintext recovery codes."""
    codes = []
    for _ in range(count):
        parts = [
            "".join(secrets.choice(_ALPHABET) for _ in range(GROUP_LEN))
            for _ in range(GROUPS)
        ]
        codes.append("-".join(parts))
    return codes


def _normalize(code: str) -> str:
    return (code or "").strip().lower().replace(" ", "")


def hash_codes(codes: list[str]) -> str:
    """Return a JSON blob of hashed codes for storage on the user row."""
    return json.dumps([generate_password_hash(_normalize(c)) for c in codes])


def _load(blob: str | None) -> list[str]:
    if not blob:
        return []
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def remaining_count(blob: str | None) -> int:
    return len(_load(blob))


def looks_like_recovery_code(code: str) -> bool:
    """Cheap shape check so a 6-digit TOTP isn't tried as a recovery code."""
    normalized = _normalize(code)
    return "-" in normalized or (normalized.isalnum() and not normalized.isdigit())


def verify_and_consume(user, submitted: str) -> bool:
    """If ``submitted`` matches one of the user's codes, consume it and return True.

    The caller is responsible for committing the transaction.
    """
    normalized = _normalize(submitted)
    if not normalized:
        return False
    hashes = _load(user.mfa_recovery_codes)
    for index, hashed in enumerate(hashes):
        if check_password_hash(hashed, normalized):
            hashes.pop(index)
            user.mfa_recovery_codes = json.dumps(hashes)
            return True
    return False
