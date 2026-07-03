"""Shared route helpers and authorization policy."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, flash, g, jsonify, redirect, request, session, url_for

from models import User, db

ALERT_MANAGER_ROLES = {"Admin", "Supervisor"}
REPORT_VIEWER_ROLES = {"Admin", "Supervisor"}
INSPECTION_OPERATOR_ROLES = {"Admin", "Operator", "Inspector"}
INSPECTION_REVIEWER_ROLES = {"Admin", "Supervisor", "Inspector"}
ADMIN_ROLES = {"Admin"}


def wants_json_response():
    """Return True when the client expects a JSON API response."""
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )


def pagination_args(default_per_page=25, max_per_page=100):
    """Return bounded page/per_page values from query parameters."""
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", default_per_page, type=int) or default_per_page
    return max(page, 1), min(max(per_page, 1), max_per_page)


def form_error(message, endpoint="new_inspection", status=400):
    """Return an error for API callers or flash/redirect for browser form posts."""
    if wants_json_response():
        return jsonify({"error": message}), status
    flash(message, "error")
    return redirect(url_for(endpoint))


def clean_metadata_value(raw, *, max_length, field_name, uppercase=False, allow_empty=True):
    """Normalize and length-check free-text inspection metadata."""
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if uppercase:
        value = value.upper()
    if not value:
        if allow_empty:
            return None, None
        return None, f"{field_name} is required."
    if len(value) > max_length:
        return None, f"{field_name} must be {max_length} characters or fewer."
    return value, None


def normalize_plate(raw):
    """Normalize plate text while preserving common alphanumeric-hyphen format."""
    value = re.sub(r"[\s_]+", "-", (raw or "").strip().upper())
    value = re.sub(r"[^A-Z0-9-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value:
        return None, None
    if len(value) > 20:
        return None, "Plate must be 20 characters or fewer."
    return value, None


def parse_report_range(max_days):
    """Parse and validate report date range query parameters."""
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return None, None, date_from, date_to, (jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400)
    if end <= start:
        return None, None, date_from, date_to, (jsonify({"error": "Date range must end after it starts."}), 400)
    if (end - start).days > max_days:
        return None, None, date_from, date_to, (
            jsonify({"error": f"Date range cannot exceed {max_days} days."}),
            400,
        )
    return start, end, date_from, date_to, None


def report_day_labels(start, end):
    """Return continuous YYYY-MM-DD keys and display labels for a report range."""
    keys = []
    labels = []
    current = start
    while current < end:
        keys.append(current.strftime("%Y-%m-%d"))
        labels.append(current.strftime("%b %d"))
        current += timedelta(days=1)
    return keys, labels


def auth_failure_response():
    """Return a 401 JSON for API/XHR callers, otherwise redirect to login."""
    if request.path.startswith("/api/") or wants_json_response():
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for("login"))


def authorization_failure_response():
    """Return a 403 response appropriate for browser or API callers."""
    if request.path.startswith("/api/") or wants_json_response():
        return jsonify({"error": "Forbidden"}), 403
    abort(403)


def session_user():
    """Load the current user from the session and refresh role from the DB."""
    user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = db.session.get(User, user_id)
    if user is None and session.get("user"):
        user = User.query.filter_by(email=session["user"]).first()
    if user is not None and not user.is_active:
        return None
    if user is not None:
        session["user_id"] = user.id
        session["user"] = user.email
        session["role"] = user.role
    return user


def roles_required(*roles):
    """Require the current authenticated user to have one of the given roles."""
    allowed_roles = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = getattr(g, "current_user", None) or session_user()
            if user is None:
                return auth_failure_response()
            if user.role not in allowed_roles:
                return authorization_failure_response()
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
