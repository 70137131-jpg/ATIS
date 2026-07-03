"""Admin operational location and camera management routes."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from models import Camera, Location, User, db
from routes.common import ADMIN_ROLES, clean_metadata_value, roles_required
from services.audit import log_audit_event
from services.operations import normalize_operational_name


def _optional_user_id(raw):
    if not raw:
        return None, None
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return None, "Choose a valid assigned user."
    if user_id <= 0:
        return None, None
    if db.session.get(User, user_id) is None:
        return None, "Choose a valid assigned user."
    return user_id, None


def _location_id(raw):
    try:
        location_id = int(raw)
    except (TypeError, ValueError):
        return None, "Choose a valid location."
    if db.session.get(Location, location_id) is None:
        return None, "Choose a valid location."
    return location_id, None


def _active_from_form():
    return request.form.get("is_active") == "on"


def _location_by_normalized(name, exclude_id=None):
    query = Location.query.filter_by(normalized_name=normalize_operational_name(name)[:200])
    if exclude_id is not None:
        query = query.filter(Location.id != exclude_id)
    return query.first()


def _camera_by_normalized(name, location_id, exclude_id=None):
    query = Camera.query.filter_by(
        normalized_name=normalize_operational_name(name)[:20],
        location_id=location_id,
    )
    if exclude_id is not None:
        query = query.filter(Camera.id != exclude_id)
    return query.first()


@roles_required(*ADMIN_ROLES)
def operations_admin():
    locations = Location.query.order_by(Location.name.asc()).all()
    cameras = (
        Camera.query
        .outerjoin(Location, Camera.location_id == Location.id)
        .order_by(Location.name.asc(), Camera.name.asc())
        .all()
    )
    assignable_users = User.query.filter_by(is_active=True).order_by(User.email.asc()).all()
    return render_template(
        "admin_operations.html",
        user=session["user"],
        role=session["role"],
        locations=locations,
        cameras=cameras,
        assignable_users=assignable_users,
    )


@roles_required(*ADMIN_ROLES)
def create_location():
    name, error = clean_metadata_value(
        request.form.get("name"),
        max_length=200,
        field_name="Location name",
        allow_empty=False,
    )
    zone, zone_error = clean_metadata_value(
        request.form.get("zone"),
        max_length=80,
        field_name="Zone",
        allow_empty=True,
    )
    if error or zone_error:
        flash(error or zone_error, "error")
        return redirect(url_for("operations_admin"))
    if _location_by_normalized(name):
        flash("A location with that name already exists.", "error")
        return redirect(url_for("operations_admin"))

    location = Location(
        name=name,
        normalized_name=normalize_operational_name(name)[:200],
        zone=zone,
        is_active=True,
    )
    db.session.add(location)
    db.session.flush()
    log_audit_event(
        "location.created",
        entity_type="location",
        entity_id=location.id,
        details={"name": location.name, "zone": location.zone},
    )
    db.session.commit()
    flash(f"Created location {location.name}.", "success")
    return redirect(url_for("operations_admin"))


@roles_required(*ADMIN_ROLES)
def update_location(location_id):
    location = db.get_or_404(Location, location_id)
    name, error = clean_metadata_value(
        request.form.get("name"),
        max_length=200,
        field_name="Location name",
        allow_empty=False,
    )
    zone, zone_error = clean_metadata_value(
        request.form.get("zone"),
        max_length=80,
        field_name="Zone",
        allow_empty=True,
    )
    if error or zone_error:
        flash(error or zone_error, "error")
        return redirect(url_for("operations_admin"))
    if _location_by_normalized(name, exclude_id=location.id):
        flash("A location with that name already exists.", "error")
        return redirect(url_for("operations_admin"))

    before = {"name": location.name, "zone": location.zone, "is_active": location.is_active}
    location.name = name
    location.normalized_name = normalize_operational_name(name)[:200]
    location.zone = zone
    location.is_active = _active_from_form()
    log_audit_event(
        "location.updated",
        entity_type="location",
        entity_id=location.id,
        details={"before": before, "after": {"name": location.name, "zone": location.zone, "is_active": location.is_active}},
    )
    db.session.commit()
    flash(f"Updated location {location.name}.", "success")
    return redirect(url_for("operations_admin"))


@roles_required(*ADMIN_ROLES)
def create_camera():
    name, error = clean_metadata_value(
        request.form.get("name"),
        max_length=20,
        field_name="Camera name",
        uppercase=True,
        allow_empty=False,
    )
    zone, zone_error = clean_metadata_value(
        request.form.get("zone"),
        max_length=80,
        field_name="Zone",
        allow_empty=True,
    )
    location_id, location_error = _location_id(request.form.get("location_id"))
    assigned_user_id, user_error = _optional_user_id(request.form.get("assigned_user_id"))
    error = error or zone_error or location_error or user_error
    if error:
        flash(error, "error")
        return redirect(url_for("operations_admin"))
    if _camera_by_normalized(name, location_id):
        flash("A camera with that name already exists for this location.", "error")
        return redirect(url_for("operations_admin"))

    camera = Camera(
        name=name,
        normalized_name=normalize_operational_name(name)[:20],
        location_id=location_id,
        zone=zone,
        assigned_user_id=assigned_user_id,
        is_active=True,
    )
    db.session.add(camera)
    db.session.flush()
    log_audit_event(
        "camera.created",
        entity_type="camera",
        entity_id=camera.id,
        details={
            "name": camera.name,
            "location_id": camera.location_id,
            "zone": camera.zone,
            "assigned_user_id": camera.assigned_user_id,
        },
    )
    db.session.commit()
    flash(f"Created camera {camera.name}.", "success")
    return redirect(url_for("operations_admin"))


@roles_required(*ADMIN_ROLES)
def update_camera(camera_id):
    camera = db.get_or_404(Camera, camera_id)
    name, error = clean_metadata_value(
        request.form.get("name"),
        max_length=20,
        field_name="Camera name",
        uppercase=True,
        allow_empty=False,
    )
    zone, zone_error = clean_metadata_value(
        request.form.get("zone"),
        max_length=80,
        field_name="Zone",
        allow_empty=True,
    )
    location_id, location_error = _location_id(request.form.get("location_id"))
    assigned_user_id, user_error = _optional_user_id(request.form.get("assigned_user_id"))
    error = error or zone_error or location_error or user_error
    if error:
        flash(error, "error")
        return redirect(url_for("operations_admin"))
    if _camera_by_normalized(name, location_id, exclude_id=camera.id):
        flash("A camera with that name already exists for this location.", "error")
        return redirect(url_for("operations_admin"))

    before = {
        "name": camera.name,
        "location_id": camera.location_id,
        "zone": camera.zone,
        "assigned_user_id": camera.assigned_user_id,
        "is_active": camera.is_active,
    }
    camera.name = name
    camera.normalized_name = normalize_operational_name(name)[:20]
    camera.location_id = location_id
    camera.zone = zone
    camera.assigned_user_id = assigned_user_id
    camera.is_active = _active_from_form()
    log_audit_event(
        "camera.updated",
        entity_type="camera",
        entity_id=camera.id,
        details={
            "before": before,
            "after": {
                "name": camera.name,
                "location_id": camera.location_id,
                "zone": camera.zone,
                "assigned_user_id": camera.assigned_user_id,
                "is_active": camera.is_active,
            },
        },
    )
    db.session.commit()
    flash(f"Updated camera {camera.name}.", "success")
    return redirect(url_for("operations_admin"))


def register_routes(app):
    app.add_url_rule("/admin/operations", "operations_admin", operations_admin)
    app.add_url_rule("/admin/operations/locations", "create_location", create_location, methods=["POST"])
    app.add_url_rule(
        "/admin/operations/locations/<int:location_id>",
        "update_location",
        update_location,
        methods=["POST"],
    )
    app.add_url_rule("/admin/operations/cameras", "create_camera", create_camera, methods=["POST"])
    app.add_url_rule(
        "/admin/operations/cameras/<int:camera_id>",
        "update_camera",
        update_camera,
        methods=["POST"],
    )
