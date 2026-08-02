"""Password-strength policy shared by every place that sets a password.

Previously the only rule was "at least 8 characters", applied inconsistently.
This centralises a stronger, configurable policy: a longer minimum length, a
small built-in block-list of obviously weak/known passwords, and a light
character-variety requirement. Keep the policy in one place so admin creation,
admin reset, and self-service change all enforce the same thing.
"""

from __future__ import annotations

import os

DEFAULT_MIN_LENGTH = 12

# A tiny embedded block-list of the most abused passwords. For a real breach
# check, wire in an offline Have-I-Been-Pwned k-anonymity range lookup; this
# stops the worst offenders without a network dependency.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "letmein", "admin", "admin123", "welcome", "welcome1",
    "iloveyou", "abc12345", "changeme", "passw0rd", "p@ssw0rd", "trustno1",
    "atis", "atis123", "atis1234", "nha12345", "operator123", "inspect123",
    "super123",
}


def min_length() -> int:
    try:
        return max(8, int(os.environ.get("ATIS_MIN_PASSWORD_LENGTH", DEFAULT_MIN_LENGTH)))
    except ValueError:
        return DEFAULT_MIN_LENGTH


def validate_password_strength(password: str, *, email: str | None = None) -> str | None:
    """Return an error message if the password is too weak, else None."""
    password = password or ""
    length = min_length()

    if len(password) < length:
        return f"Password must be at least {length} characters."
    if password.lower() in _COMMON_PASSWORDS:
        return "That password is too common. Choose a less predictable password."
    if email:
        username = email.split("@", 1)[0].lower()
        # Reject passwords that embed a non-trivial username (e.g. "Alice1234"
        # for alice@…); very short usernames are skipped to avoid false hits.
        if len(username) >= 4 and username in password.lower():
            return "Password must not contain your username."

    # Light variety check: require at least two of {lower, upper, digit, symbol}
    # so a long-but-trivial string ("aaaaaaaaaaaa") is rejected.
    classes = sum(
        bool(match)
        for match in (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )
    if classes < 2:
        return "Password must mix letters, numbers, or symbols (use at least two kinds)."

    return None
