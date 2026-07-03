"""Audit event creation helpers."""

from __future__ import annotations

import json

from flask import g, has_request_context, request

from models import AuditEvent, db


def _request_ip():
    if not has_request_context():
        return None
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr


def log_audit_event(action, *, entity_type=None, entity_id=None, details=None, actor=None):
    """Add an audit event to the current DB transaction."""
    if actor is None:
        actor = getattr(g, "current_user", None) if has_request_context() else None

    user_agent = None
    if has_request_context() and request.user_agent:
        user_agent = str(request.user_agent)[:255]

    event = AuditEvent(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=_request_ip(),
        user_agent=user_agent,
        details=json.dumps(details or {}, sort_keys=True),
    )
    db.session.add(event)
    return event
