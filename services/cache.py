"""Tiny in-process TTL cache for expensive read-mostly aggregations.

Dashboard and report queries recompute the same aggregates on every request.
This caches their results for a short, configurable window
(``ATIS_STATS_CACHE_SECONDS``) so repeated views don't repeatedly hammer the
database. It is deliberately minimal: per-process (each gunicorn worker has its
own), thread-safe, and disabled by default (TTL 0) so behaviour is unchanged
unless a deployment opts in. Bounded staleness is acceptable for a dashboard;
never use this for data that must be read-your-writes consistent.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from flask import current_app

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _ttl_seconds() -> int:
    try:
        return int(current_app.config.get("STATS_CACHE_SECONDS", 0))
    except Exception:  # noqa: BLE001 - outside app context: treat as disabled
        return 0


def get_or_compute(key: str, compute: Callable[[], Any], *, now: float | None = None) -> Any:
    """Return a cached value for ``key`` or compute, cache, and return it.

    When the configured TTL is <= 0 the cache is bypassed entirely (always
    computes), so results stay live unless caching is explicitly enabled.
    """
    ttl = _ttl_seconds()
    if ttl <= 0:
        return compute()

    clock = time.monotonic() if now is None else now
    with _lock:
        entry = _store.get(key)
        if entry is not None and entry[0] > clock:
            return entry[1]

    value = compute()
    with _lock:
        _store[key] = (clock + ttl, value)
    return value


def clear() -> None:
    """Drop all cached entries (used by tests)."""
    with _lock:
        _store.clear()
