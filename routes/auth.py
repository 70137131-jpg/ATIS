"""Authentication and dashboard routes."""

from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, render_template, request, session, url_for

from models import Alert, Inspection, User, db
from services.audit import log_audit_event
from services.cache import get_or_compute
from services.login_security import (
    is_locked,
    register_failed_attempt,
    register_successful_login,
)
from services.totp import verify as totp_verify
from services import recovery_codes


def _establish_session(user):
    """Promote a verified user to a fully authenticated session.

    Regenerates the session (fixation defence) and stamps the current epoch so
    the session can be revoked later. Callers commit the transaction.
    """
    register_successful_login(user, commit=False)
    session.clear()
    session["user_id"] = user.id
    session["user"] = user.email
    session["role"] = user.role
    session["session_epoch"] = user.session_epoch


def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        login_email = email

        if current_app.config["ENABLE_DEMO_LOGIN_ALIASES"]:
            demo_aliases = {
                "admin@nha.gov.pk": "admin@atis.com",
                "operator@nha.gov.pk": "operator@atis.com",
                "supervisor@nha.gov.pk": "supervisor@atis.com",
                "inspector@nha.gov.pk": "inspector@atis.com",
            }
            login_email = demo_aliases.get(email, email)

        user = User.query.filter_by(email=login_email).first()

        # Per-account lockout is checked before the password so a locked account
        # cannot be probed. The message is generic to avoid account enumeration.
        if user and user.is_active and is_locked(user):
            flash("Account temporarily locked after repeated failed logins. Try again later.", "error")
            return redirect(url_for("login"))

        if user and user.is_active and user.check_password(password):
            if user.mfa_enabled and user.mfa_secret:
                # Password is correct but a second factor is required. Stash a
                # short-lived pending marker; do NOT authenticate yet.
                session.clear()
                session["mfa_pending_user_id"] = user.id
                log_audit_event(
                    "auth.password_ok_mfa_required",
                    entity_type="user",
                    entity_id=user.id,
                    actor=user,
                )
                db.session.commit()
                return redirect(url_for("mfa_verify"))

            _establish_session(user)
            log_audit_event("auth.login_succeeded", entity_type="user", entity_id=user.id, actor=user)
            db.session.commit()
            return redirect(url_for("dashboard"))

        # Only count failures against a real, active account.
        if user and user.is_active:
            locked = register_failed_attempt(user, commit=False)
            log_audit_event(
                "auth.login_locked" if locked else "auth.login_failed",
                entity_type="user",
                entity_id=user.id,
                actor=user,
            )
            db.session.commit()

        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


def _utc_day_start():
    """Return midnight UTC for the current day.

    Inspection.timestamp is stored naive-UTC (see the datetime convention in
    CLAUDE.md), so the day boundary must be built in UTC too. A naive
    datetime.now() would take the *host's local* wall clock and compare it
    against UTC-stored rows, shifting the "today" window by the host's UTC
    offset on any non-UTC machine.
    """
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _compute_dashboard_stats():
    today_start = _utc_day_start()
    tomorrow_start = today_start + timedelta(days=1)
    today_filter = (
        Inspection.timestamp >= today_start,
        Inspection.timestamp < tomorrow_start,
    )
    total_today = db.session.scalar(
        db.select(db.func.count()).select_from(Inspection).where(*today_filter)
    ) or 0
    safe_today = db.session.scalar(
        db.select(db.func.count()).select_from(Inspection).where(*today_filter, Inspection.status == "safe")
    ) or 0
    unsafe_today = db.session.scalar(
        db.select(db.func.count()).select_from(Inspection).where(*today_filter, Inspection.status != "safe")
    ) or 0
    all_time_total = Inspection.query.count()
    pending_alerts = Alert.query.filter_by(status="pending").count()
    pass_rate = round((safe_today / total_today * 100), 1) if total_today > 0 else 0
    avg_processing_ms = db.session.scalar(
        db.select(db.func.avg(Inspection.inference_ms)).where(
            *today_filter,
            Inspection.inference_ms.is_not(None),
        )
    )
    return {
        "total": total_today,
        "safe": safe_today,
        "unsafe": unsafe_today,
        "all_time_total": all_time_total,
        "pending_alerts": pending_alerts,
        "pass_rate": pass_rate,
        "avg_processing_ms": int(round(avg_processing_ms)) if avg_processing_ms is not None else None,
    }


def dashboard():
    inspections = Inspection.query.order_by(Inspection.timestamp.desc()).limit(10).all()

    # Cached for the configured short TTL (keyed by UTC day, matching the window
    # _compute_dashboard_stats uses, so "today" buckets roll over together);
    # disabled by default, so numbers are live unless enabled.
    stats = get_or_compute(
        f"dashboard_stats:{_utc_day_start().date().isoformat()}",
        _compute_dashboard_stats,
    )

    recent_alerts = (
        Alert.query
        .join(Inspection)
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "index.html",
        user=session["user"],
        role=session["role"],
        inspections=inspections,
        stats=stats,
        recent_alerts=recent_alerts,
    )


def mfa_verify():
    """Second-factor step: shown after a correct password when MFA is enabled."""
    user_id = session.get("mfa_pending_user_id")
    if not user_id:
        return redirect(url_for("login"))
    user = db.session.get(User, user_id)
    if user is None or not user.is_active or not user.mfa_enabled:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        # The 6-digit code is brute-forceable, so MFA failures feed the same
        # per-account lockout as password failures.
        if is_locked(user):
            session.clear()
            flash("Account temporarily locked after repeated failed attempts. Try again later.", "error")
            return redirect(url_for("login"))

        code = request.form.get("code", "")
        if totp_verify(user.mfa_secret, code):
            _establish_session(user)
            log_audit_event("auth.mfa_succeeded", entity_type="user", entity_id=user.id, actor=user)
            db.session.commit()
            return redirect(url_for("dashboard"))

        # Fall back to a single-use recovery code (consumes it on success).
        if recovery_codes.looks_like_recovery_code(code) and recovery_codes.verify_and_consume(user, code):
            _establish_session(user)
            remaining = recovery_codes.remaining_count(user.mfa_recovery_codes)
            log_audit_event(
                "auth.mfa_recovery_used",
                entity_type="user",
                entity_id=user.id,
                actor=user,
                details={"remaining": remaining},
            )
            db.session.commit()
            flash(f"Signed in with a recovery code. {remaining} recovery code(s) remaining.", "warning")
            return redirect(url_for("dashboard"))

        register_failed_attempt(user, commit=False)
        log_audit_event("auth.mfa_failed", entity_type="user", entity_id=user.id, actor=user)
        db.session.commit()
        flash("Invalid authentication code.", "error")
        return redirect(url_for("mfa_verify"))

    return render_template("mfa_verify.html")


def logout():
    session.clear()
    return redirect(url_for("login"))


def register_routes(app, limiter):
    app.add_url_rule("/", "index", index)
    app.add_url_rule("/login", "login", limiter.limit("10 per minute", methods=["POST"])(login), methods=["GET", "POST"])
    app.add_url_rule(
        "/mfa/verify",
        "mfa_verify",
        limiter.limit("10 per minute", methods=["POST"])(mfa_verify),
        methods=["GET", "POST"],
    )
    app.add_url_rule("/dashboard", "dashboard", dashboard)
    app.add_url_rule("/logout", "logout", logout)
