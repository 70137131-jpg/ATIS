"""Admin user management and account password routes."""

from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from models import User, db
from routes.common import ADMIN_ROLES, roles_required
from services.audit import log_audit_event


VALID_ROLES = ("Admin", "Supervisor", "Operator", "Inspector")
MIN_PASSWORD_LENGTH = 8


def _normalize_email(raw):
    return (raw or "").strip().lower()


def _validate_role(role):
    return role if role in VALID_ROLES else None


@roles_required(*ADMIN_ROLES)
def admin_users():
    """List users and create new accounts."""
    if request.method == "POST":
        email = _normalize_email(request.form.get("email"))
        role = _validate_role(request.form.get("role", "Operator"))
        password = request.form.get("password", "")

        if not email or "@" not in email:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("admin_users"))
        if role is None:
            flash("Choose a valid role.", "error")
            return redirect(url_for("admin_users"))
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
            return redirect(url_for("admin_users"))
        if User.query.filter_by(email=email).first():
            flash("A user with that email already exists.", "error")
            return redirect(url_for("admin_users"))

        user = User(email=email, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        log_audit_event(
            "user.created",
            entity_type="user",
            entity_id=user.id,
            details={"email": user.email, "role": user.role},
        )
        db.session.commit()
        flash(f"Created {email}.", "success")
        return redirect(url_for("admin_users"))

    users = User.query.order_by(User.email.asc()).all()
    return render_template(
        "admin_users.html",
        user=session["user"],
        role=session["role"],
        users=users,
        valid_roles=VALID_ROLES,
        current_user_id=g.current_user.id,
    )


@roles_required(*ADMIN_ROLES)
def update_user_role(user_id):
    user = db.get_or_404(User, user_id)
    role = _validate_role(request.form.get("role"))
    if role is None:
        flash("Choose a valid role.", "error")
        return redirect(url_for("admin_users"))
    old_role = user.role
    user.role = role
    log_audit_event(
        "user.role_changed",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "from_role": old_role, "to_role": role},
    )
    db.session.commit()
    if user.id == g.current_user.id:
        session["role"] = role
    flash(f"Updated role for {user.email}.", "success")
    return redirect(url_for("admin_users"))


@roles_required(*ADMIN_ROLES)
def set_user_active(user_id, active):
    user = db.get_or_404(User, user_id)
    if user.id == g.current_user.id and not active:
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("admin_users"))
    old_active = user.is_active
    user.is_active = active
    log_audit_event(
        "user.enabled" if active else "user.disabled",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "from_active": old_active, "to_active": active},
    )
    db.session.commit()
    action = "enabled" if active else "disabled"
    flash(f"{user.email} {action}.", "success")
    return redirect(url_for("admin_users"))


@roles_required(*ADMIN_ROLES)
def reset_user_password(user_id):
    user = db.get_or_404(User, user_id)
    password = request.form.get("password", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        return redirect(url_for("admin_users"))
    user.set_password(password)
    log_audit_event(
        "user.password_reset",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email},
    )
    db.session.commit()
    flash(f"Password reset for {user.email}.", "success")
    return redirect(url_for("admin_users"))


def change_password():
    """Let the current user change their own password."""
    if request.method == "POST":
        user = g.current_user
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not user.check_password(current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("change_password"))
        if len(new_password) < MIN_PASSWORD_LENGTH:
            flash(f"New password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
            return redirect(url_for("change_password"))
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("change_password"))

        user.set_password(new_password)
        log_audit_event(
            "user.password_changed",
            entity_type="user",
            entity_id=user.id,
            details={"email": user.email},
        )
        db.session.commit()
        flash("Password changed.", "success")
        return redirect(url_for("dashboard"))

    return render_template("change_password.html", user=session["user"], role=session["role"])


def register_routes(app):
    app.add_url_rule("/admin/users", "admin_users", admin_users, methods=["GET", "POST"])
    app.add_url_rule("/admin/users/<int:user_id>/role", "update_user_role", update_user_role, methods=["POST"])
    app.add_url_rule(
        "/admin/users/<int:user_id>/disable",
        "disable_user",
        lambda user_id: set_user_active(user_id, False),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users/<int:user_id>/enable",
        "enable_user",
        lambda user_id: set_user_active(user_id, True),
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users/<int:user_id>/password",
        "reset_user_password",
        reset_user_password,
        methods=["POST"],
    )
    app.add_url_rule("/account/password", "change_password", change_password, methods=["GET", "POST"])
