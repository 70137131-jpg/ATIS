"""Operational location and camera admin tests."""

from models import AuditEvent, Camera, Location, User, db


def _auth_as(client, app, email, role, password="password123"):
    with app.app_context():
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user"] = email
        sess["role"] = role
    return user_id


def test_admin_can_create_and_update_operations_catalog(client, app):
    admin_id = _auth_as(client, app, "ops-admin@example.com", "Admin")

    create_location = client.post(
        "/admin/operations/locations",
        data={"name": "  North Toll Plaza  ", "zone": "Zone A"},
        follow_redirects=False,
    )

    assert create_location.status_code in (302, 303)
    with app.app_context():
        location = Location.query.filter_by(normalized_name="north toll plaza").one()
        assert location.name == "North Toll Plaza"
        assert location.zone == "Zone A"
        location_id = location.id

    create_camera = client.post(
        "/admin/operations/cameras",
        data={
            "name": " cam-07 ",
            "location_id": str(location_id),
            "zone": "Lane 7",
            "assigned_user_id": str(admin_id),
        },
        follow_redirects=False,
    )

    assert create_camera.status_code in (302, 303)
    with app.app_context():
        camera = Camera.query.filter_by(normalized_name="cam-07", location_id=location_id).one()
        assert camera.name == "CAM-07"
        assert camera.zone == "Lane 7"
        assert camera.assigned_user_id == admin_id
        camera_id = camera.id

    update_camera = client.post(
        f"/admin/operations/cameras/{camera_id}",
        data={
            "name": "cam-08",
            "location_id": str(location_id),
            "zone": "Lane 8",
            "assigned_user_id": "",
        },
        follow_redirects=False,
    )

    assert update_camera.status_code in (302, 303)
    with app.app_context():
        camera = db.session.get(Camera, camera_id)
        assert camera.name == "CAM-08"
        assert camera.zone == "Lane 8"
        assert camera.assigned_user_id is None
        assert not camera.is_active
        actions = [event.action for event in AuditEvent.query.order_by(AuditEvent.id.asc()).all()]
        assert "location.created" in actions
        assert "camera.created" in actions
        assert "camera.updated" in actions


def test_operations_admin_rejects_duplicate_location_names(client, app):
    _auth_as(client, app, "ops-duplicates@example.com", "Admin")
    with app.app_context():
        db.session.add(Location(name="Gate One", normalized_name="gate one", is_active=True))
        db.session.commit()

    response = client.post(
        "/admin/operations/locations",
        data={"name": " gate   one ", "zone": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"already exists" in response.data
    with app.app_context():
        assert Location.query.count() == 1


def test_operator_cannot_manage_operations_catalog(client, app):
    _auth_as(client, app, "ops-operator@example.com", "Operator")

    response = client.get("/admin/operations", follow_redirects=False)

    assert response.status_code == 403
