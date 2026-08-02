"""Per-account login throttling and lockout.

The Flask-Limiter rate limit on ``/login`` is per **IP**, so it does nothing
against distributed credential stuffing that spreads attempts across many
addresses at one account. This module adds a per-**account** throttle: after
``ATIS_MAX_LOGIN_ATTEMPTS`` consecutive failures the account is locked for
``ATIS_LOCKOUT_MINUTES``. A successful login clears the counter.

The lock is deliberately checked *before* the password is verified so a locked
account cannot be probed, and enumeration is avoided by giving the caller a
generic message.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from models import db

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def max_attempts() -> int:
    try:
        return max(1, int(os.environ.get("ATIS_MAX_LOGIN_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)))
    except ValueError:
        return DEFAULT_MAX_ATTEMPTS


def lockout_minutes() -> int:
    try:
        return max(1, int(os.environ.get("ATIS_LOCKOUT_MINUTES", DEFAULT_LOCKOUT_MINUTES)))
    except ValueError:
        return DEFAULT_LOCKOUT_MINUTES


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a possibly naive DB datetime to aware UTC for comparison."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_locked(user, *, now: datetime | None = None) -> bool:
    """Return True if the account is currently within its lockout window."""
    locked_until = _as_utc(getattr(user, "locked_until", None))
    if locked_until is None:
        return False
    return (now or _utcnow()) < locked_until


def register_failed_attempt(user, *, now: datetime | None = None, commit: bool = True) -> bool:
    """Record one failed login; lock the account if the threshold is reached.

    Returns True if this attempt tripped (or extended) a lock.
    """
    now = now or _utcnow()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    locked = False
    if user.failed_login_count >= max_attempts():
        user.locked_until = now + timedelta(minutes=lockout_minutes())
        locked = True
    if commit:
        db.session.commit()
    return locked


def register_successful_login(user, *, now: datetime | None = None, commit: bool = True) -> None:
    """Clear the failure counter and any lock after a valid login."""
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now or _utcnow()
    if commit:
        db.session.commit()
