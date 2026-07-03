"""Alert listing and workflow action routes."""

from datetime import datetime, timezone

from flask import flash, g, jsonify, redirect, render_template, request, session, url_for

from models import Alert, AlertComment, Inspection, User, db
from routes.common import (
    ALERT_MANAGER_ROLES,
    pagination_args,
    roles_required,
    wants_json_response,
)
from services.audit import log_audit_event

ALERT_PRIORITIES = ("low", "medium", "high", "critical")
ALERT_SEVERITIES = ("minor", "major", "critical")
ESCALATION_STATUSES = ("none", "monitoring", "escalated", "sla_breached")
RESOLUTION_CATEGORIES = ("", "tyre_replaced", "driver_warned", "false_alarm", "duplicate", "no_action_required", "other")
ALERT_TEAMS = ("", "Checkpoint Team", "Mobile Response", "Maintenance", "Supervisor Desk")
MAX_ALERT_COMMENT_LENGTH = 2000


def _valid_or_default(value, valid_values, default):
    value = (value or "").strip()
    return value if value in valid_values else default


def _parse_sla_due_at(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _format_sla_due_at(value):
    if not value:
        return ""
    return value.strftime("%Y-%m-%dT%H:%M")


def _add_alert_history(alert, body, *, comment_type="workflow"):
    comment = AlertComment(
        alert_id=alert.id,
        author_id=g.current_user.id if getattr(g, "current_user", None) else None,
        comment_type=comment_type,
        body=body,
    )
    db.session.add(comment)
    return comment


@roles_required(*ALERT_MANAGER_ROLES)
def alerts():
    page, per_page = pagination_args()
    alert_query = (
        db.select(Alert)
        .join(Inspection)
        .order_by(Alert.created_at.desc())
    )
    pagination = db.paginate(alert_query, page=page, per_page=per_page, error_out=False)
    alert_rows = pagination.items
    pending_count = Alert.query.filter_by(status="pending").count()
    users = User.query.filter_by(is_active=True).order_by(User.email.asc()).all()

    return render_template(
        "alerts.html",
        user=session["user"],
        role=session["role"],
        alerts=alert_rows,
        pending_count=pending_count,
        pagination=pagination,
        users=users,
        priorities=ALERT_PRIORITIES,
        severities=ALERT_SEVERITIES,
        escalation_statuses=ESCALATION_STATUSES,
        resolution_categories=RESOLUTION_CATEGORIES,
        alert_teams=ALERT_TEAMS,
        format_sla_due_at=_format_sla_due_at,
    )


def _alert_response(alert):
    """Return an alert payload for API callers after a workflow action."""
    return jsonify({
        "id": alert.id,
        "inspection_id": alert.inspection_id,
        "status": alert.status,
        "response": alert.response,
        "priority": alert.priority,
        "severity": alert.severity,
        "assigned_user": alert.assigned_user.email if alert.assigned_user else None,
        "assigned_team": alert.assigned_team,
        "sla_due_at": alert.sla_due_at.isoformat() if alert.sla_due_at else None,
        "escalation_status": alert.escalation_status,
        "resolution_category": alert.resolution_category,
        "acknowledged_by": alert.acknowledged_by.email if alert.acknowledged_by else None,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolved_by": alert.resolved_by.email if alert.resolved_by else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    })


@roles_required(*ALERT_MANAGER_ROLES)
def acknowledge_alert(alert_id):
    """Mark an alert acknowledged by the current operator."""
    alert = db.get_or_404(Alert, alert_id)
    if alert.status != "resolved":
        old_status = alert.status
        note = request.form.get("response", "").strip()
        user = g.current_user
        alert.status = "acknowledged"
        alert.response = note or alert.response or f"Acknowledged by {user.email}"
        alert.acknowledged_by_id = user.id
        alert.acknowledged_at = datetime.now(timezone.utc)
        _add_alert_history(alert, f"Alert acknowledged by {user.email}.")
        log_audit_event(
            "alert.acknowledged",
            entity_type="alert",
            entity_id=alert.id,
            details={
                "inspection_id": alert.inspection_id,
                "from_status": old_status,
                "to_status": alert.status,
                "has_note": bool(note),
            },
        )
        db.session.commit()
        flash(f"Alert #{alert.id} acknowledged.", "success")
    else:
        flash(f"Alert #{alert.id} is already resolved.", "warning")

    if wants_json_response():
        return _alert_response(alert)
    return redirect(url_for("alerts"))


@roles_required(*ALERT_MANAGER_ROLES)
def resolve_alert(alert_id):
    """Mark an alert resolved by the current operator."""
    alert = db.get_or_404(Alert, alert_id)
    old_status = alert.status
    note = request.form.get("response", "").strip()
    resolution_category = _valid_or_default(
        request.form.get("resolution_category"),
        RESOLUTION_CATEGORIES,
        alert.resolution_category or "",
    )
    user = g.current_user
    alert.status = "resolved"
    alert.response = note or alert.response or f"Resolved by {user.email}"
    alert.resolution_category = resolution_category or alert.resolution_category
    if alert.acknowledged_by_id is None:
        alert.acknowledged_by_id = user.id
        alert.acknowledged_at = datetime.now(timezone.utc)
    alert.resolved_by_id = user.id
    alert.resolved_at = datetime.now(timezone.utc)
    _add_alert_history(alert, f"Alert resolved by {user.email}.")
    log_audit_event(
        "alert.resolved",
        entity_type="alert",
        entity_id=alert.id,
        details={
            "inspection_id": alert.inspection_id,
            "from_status": old_status,
            "to_status": alert.status,
            "has_note": bool(note),
            "resolution_category": alert.resolution_category,
        },
    )
    db.session.commit()
    flash(f"Alert #{alert.id} resolved.", "success")

    if wants_json_response():
        return _alert_response(alert)
    return redirect(url_for("alerts"))


@roles_required(*ALERT_MANAGER_ROLES)
def update_alert_details(alert_id):
    """Update assignment, priority/severity, SLA, escalation, and resolution metadata."""
    alert = db.get_or_404(Alert, alert_id)
    old_values = {
        "priority": alert.priority,
        "severity": alert.severity,
        "assigned_user_id": alert.assigned_user_id,
        "assigned_team": alert.assigned_team,
        "sla_due_at": alert.sla_due_at.isoformat() if alert.sla_due_at else None,
        "escalation_status": alert.escalation_status,
        "resolution_category": alert.resolution_category,
    }

    assigned_user_id = request.form.get("assigned_user_id", "").strip()
    assigned_user = db.session.get(User, int(assigned_user_id)) if assigned_user_id.isdigit() else None
    alert.assigned_user_id = assigned_user.id if assigned_user else None
    alert.assigned_team = (request.form.get("assigned_team") or "").strip()[:80] or None
    alert.priority = _valid_or_default(request.form.get("priority"), ALERT_PRIORITIES, alert.priority or "medium")
    alert.severity = _valid_or_default(request.form.get("severity"), ALERT_SEVERITIES, alert.severity or "major")
    alert.escalation_status = _valid_or_default(
        request.form.get("escalation_status"),
        ESCALATION_STATUSES,
        alert.escalation_status or "none",
    )
    resolution_category = _valid_or_default(
        request.form.get("resolution_category"),
        RESOLUTION_CATEGORIES,
        alert.resolution_category or "",
    )
    alert.resolution_category = resolution_category or None
    alert.sla_due_at = _parse_sla_due_at(request.form.get("sla_due_at"))

    new_values = {
        "priority": alert.priority,
        "severity": alert.severity,
        "assigned_user_id": alert.assigned_user_id,
        "assigned_team": alert.assigned_team,
        "sla_due_at": alert.sla_due_at.isoformat() if alert.sla_due_at else None,
        "escalation_status": alert.escalation_status,
        "resolution_category": alert.resolution_category,
    }
    _add_alert_history(alert, "Alert routing and SLA metadata updated.")
    log_audit_event(
        "alert.details_updated",
        entity_type="alert",
        entity_id=alert.id,
        details={
            "inspection_id": alert.inspection_id,
            "from": old_values,
            "to": new_values,
        },
    )
    db.session.commit()
    flash(f"Alert #{alert.id} details updated.", "success")

    if wants_json_response():
        return _alert_response(alert)
    return redirect(url_for("alerts"))


@roles_required(*ALERT_MANAGER_ROLES)
def add_alert_comment(alert_id):
    """Append an operator comment to an alert's visible history."""
    alert = db.get_or_404(Alert, alert_id)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Enter a comment before saving.", "error")
        return redirect(url_for("alerts"))
    if len(body) > MAX_ALERT_COMMENT_LENGTH:
        flash(f"Alert comments must be {MAX_ALERT_COMMENT_LENGTH} characters or fewer.", "error")
        return redirect(url_for("alerts"))

    _add_alert_history(alert, body, comment_type="comment")
    log_audit_event(
        "alert.comment_added",
        entity_type="alert",
        entity_id=alert.id,
        details={"inspection_id": alert.inspection_id, "length": len(body)},
    )
    db.session.commit()
    flash(f"Comment added to alert #{alert.id}.", "success")

    if wants_json_response():
        return _alert_response(alert)
    return redirect(url_for("alerts"))


def register_routes(app):
    app.add_url_rule("/alerts", "alerts", alerts)
    app.add_url_rule(
        "/alerts/<int:alert_id>/acknowledge",
        "acknowledge_alert",
        acknowledge_alert,
        methods=["POST"],
    )
    app.add_url_rule(
        "/alerts/<int:alert_id>/resolve",
        "resolve_alert",
        resolve_alert,
        methods=["POST"],
    )
    app.add_url_rule(
        "/alerts/<int:alert_id>/details",
        "update_alert_details",
        update_alert_details,
        methods=["POST"],
    )
    app.add_url_rule(
        "/alerts/<int:alert_id>/comments",
        "add_alert_comment",
        add_alert_comment,
        methods=["POST"],
    )
