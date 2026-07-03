"""Authentication and dashboard routes."""

from datetime import datetime, timedelta

from flask import current_app, flash, redirect, render_template, request, session, url_for

from models import Alert, Inspection, User, db


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
        if user and user.is_active and user.check_password(password):
            session["user_id"] = user.id
            session["user"] = user.email
            session["role"] = user.role
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


def dashboard():
    inspections = Inspection.query.order_by(Inspection.timestamp.desc()).limit(10).all()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
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

    stats = {
        "total": total_today,
        "safe": safe_today,
        "unsafe": unsafe_today,
        "all_time_total": all_time_total,
        "pending_alerts": pending_alerts,
        "pass_rate": pass_rate,
        "avg_processing_ms": int(round(avg_processing_ms)) if avg_processing_ms is not None else None,
    }

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


def logout():
    session.clear()
    return redirect(url_for("login"))


def register_routes(app, limiter):
    app.add_url_rule("/", "index", index)
    app.add_url_rule("/login", "login", limiter.limit("10 per minute", methods=["POST"])(login), methods=["GET", "POST"])
    app.add_url_rule("/dashboard", "dashboard", dashboard)
    app.add_url_rule("/logout", "logout", logout)
