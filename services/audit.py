"""Audit event creation helpers with a tamper-evident hash chain.

Every audit event stores ``entry_hash`` = SHA-256 over its own immutable content
plus the ``entry_hash`` of the event before it. Editing or deleting any row
therefore breaks the chain from that row onward, which ``verify_audit_chain``
detects — turning "immutable by convention" into "tamper-evident in fact".

Chaining assumes audit writes are serialized (true for the default single
gunicorn worker). Under concurrent writers two events could share a predecessor
hash; a hardened multi-writer deployment should serialize audit writes (a DB
sequence/advisory lock) or ship to an append-only/WORM sink. This is a detection
mechanism, not prevention: it makes tampering evident, it does not stop a DB
admin from rewriting the whole chain.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from flask import g, has_request_context, request

from models import AuditEvent, db

# prev_hash value for the first event in the chain (no predecessor).
GENESIS_HASH = ""


def _request_ip():
    if not has_request_context():
        return None
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr


def _canonical_dt(value: datetime | None) -> str | None:
    """Canonical UTC-naive timestamp string that survives a DB round-trip.

    created_at is written tz-aware (UTC) but SQLite reads it back naive, so the
    hash must normalise both to the same string: convert any aware value to UTC
    and drop the tzinfo, then format with fixed microsecond precision.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _canonical_payload(event: AuditEvent, prev_hash: str) -> str:
    """Deterministic serialization of the fields the hash commits to."""
    return json.dumps(
        {
            "created_at": _canonical_dt(event.created_at),
            "actor_id": event.actor_id,
            "actor_email": event.actor_email,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "details": event.details,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        default=str,
    )


def compute_entry_hash(event: AuditEvent, prev_hash: str) -> str:
    return sha256(_canonical_payload(event, prev_hash).encode("utf-8")).hexdigest()


def _current_chain_head() -> str:
    """Return the entry_hash of the most recent chained event, or GENESIS.

    Autoflush makes events added earlier in the *same* transaction visible here,
    so several events written in one request chain correctly among themselves.
    """
    latest = (
        db.session.query(AuditEvent.entry_hash)
        .filter(AuditEvent.entry_hash.is_not(None))
        .order_by(AuditEvent.id.desc())
        .first()
    )
    return latest[0] if latest and latest[0] else GENESIS_HASH


def log_audit_event(action, *, entity_type=None, entity_id=None, details=None, actor=None):
    """Add a hash-chained audit event to the current DB transaction."""
    if actor is None:
        actor = getattr(g, "current_user", None) if has_request_context() else None

    user_agent = None
    if has_request_context() and request.user_agent:
        user_agent = str(request.user_agent)[:255]

    event = AuditEvent(
        # Set created_at explicitly (not via column default) so it is fixed at
        # hash time rather than at flush time.
        created_at=datetime.now(timezone.utc),
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=_request_ip(),
        user_agent=user_agent,
        details=json.dumps(details or {}, sort_keys=True),
    )

    prev_hash = _current_chain_head()
    event.prev_hash = prev_hash
    event.entry_hash = compute_entry_hash(event, prev_hash)

    db.session.add(event)
    # Flush so this event becomes the visible chain head for any subsequent event
    # written in the same transaction.
    db.session.flush()
    return event


def verify_audit_chain(*, limit: int | None = None) -> dict:
    """Recompute the chain and report the first break, if any.

    Legacy rows with no ``entry_hash`` (written before the chain existed) are
    skipped and counted separately; verification runs over the chained rows in id
    order.
    """
    query = AuditEvent.query.order_by(AuditEvent.id.asc())
    events = query.all()

    checked = 0
    legacy = 0
    running_prev = GENESIS_HASH
    first_broken_id = None
    broken_reason = None

    for event in events:
        if event.entry_hash is None:
            legacy += 1
            continue

        expected_prev = running_prev
        if event.prev_hash != expected_prev:
            first_broken_id = event.id
            broken_reason = "prev_hash does not match the previous event's hash"
            break

        recomputed = compute_entry_hash(event, event.prev_hash or GENESIS_HASH)
        if recomputed != event.entry_hash:
            first_broken_id = event.id
            broken_reason = "entry_hash does not match recomputed content hash"
            break

        running_prev = event.entry_hash
        checked += 1
        if limit is not None and checked >= limit:
            break

    return {
        "ok": first_broken_id is None,
        "checked": checked,
        "legacy_unchained": legacy,
        "total": len(events),
        "first_broken_id": first_broken_id,
        "reason": broken_reason,
    }
