"""Audit event browsing routes."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import render_template, request, session

from models import AuditEvent, db
from routes.common import ADMIN_ROLES, pagination_args, roles_required


def _audit_filters():
    return {
        "action": (request.args.get("action") or "").strip(),
        "actor": (request.args.get("actor") or "").strip(),
        "entity_type": (request.args.get("entity_type") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None


def _pagination_params():
    params = request.args.to_dict(flat=True)
    params.pop("page", None)
    params.pop("per_page", None)
    return params


@roles_required(*ADMIN_ROLES)
def audit_events():
    page, per_page = pagination_args(default_per_page=50)
    filters = _audit_filters()
    query = db.select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())

    if filters["action"]:
        query = query.where(AuditEvent.action.ilike(f"%{filters['action']}%"))
    if filters["actor"]:
        query = query.where(AuditEvent.actor_email.ilike(f"%{filters['actor']}%"))
    if filters["entity_type"]:
        query = query.where(AuditEvent.entity_type == filters["entity_type"])

    date_from = _parse_date(filters["date_from"])
    date_to = _parse_date(filters["date_to"])
    if date_from:
        query = query.where(AuditEvent.created_at >= date_from)
    if date_to:
        query = query.where(AuditEvent.created_at < date_to + timedelta(days=1))

    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    entity_types = [
        value for (value,) in db.session.execute(
            db.select(AuditEvent.entity_type)
            .where(AuditEvent.entity_type.is_not(None))
            .distinct()
            .order_by(AuditEvent.entity_type.asc())
        ).all()
    ]

    return render_template(
        "audit_events.html",
        user=session["user"],
        role=session["role"],
        events=pagination.items,
        pagination=pagination,
        filters=filters,
        entity_types=entity_types,
        pagination_params=_pagination_params(),
    )


def register_routes(app):
    app.add_url_rule("/admin/audit", "audit_events", audit_events)
