"""Server-side inspection history filter tests."""

from datetime import datetime

from models import Camera, DefectType, Inspection, InspectionDefect, Location, SavedFilter, User, db


def _seed_history_rows(app):
    with app.app_context():
        operator = User(email="operator-filter@example.com", role="Operator")
        supervisor = User(email="supervisor-filter@example.com", role="Supervisor")
        operator.set_password("password123")
        supervisor.set_password("password123")
        crack = DefectType(name="Crack", normalized_name="crack")
        bulge = DefectType(name="Bulge", normalized_name="bulge")
        db.session.add_all([operator, supervisor, crack, bulge])
        db.session.flush()

        rows = [
            Inspection(
                timestamp=datetime(2026, 6, 1, 9),
                plate="ABC-123",
                location="North Gate",
                camera="CAM-A",
                status="unsafe",
                confidence=80,
                created_by_id=operator.id,
                image_checksum="dup-checksum",
            ),
            Inspection(
                timestamp=datetime(2026, 6, 2, 9),
                plate="XYZ-999",
                location="South Gate",
                camera="CAM-B",
                status="safe",
                confidence=95,
                created_by_id=supervisor.id,
                image_checksum="unique-checksum",
            ),
            Inspection(
                timestamp=datetime(2026, 6, 3, 9),
                plate="DUP-222",
                location="North Gate",
                camera="CAM-C",
                status="unsafe",
                confidence=70,
                created_by_id=operator.id,
                image_checksum="dup-checksum",
            ),
        ]
        db.session.add_all(rows)
        db.session.flush()
        db.session.add_all([
            InspectionDefect(inspection_id=rows[0].id, defect_type_id=crack.id, confidence=80),
            InspectionDefect(inspection_id=rows[2].id, defect_type_id=bulge.id, confidence=70),
        ])
        db.session.commit()
        return {
            "operator_id": operator.id,
            "supervisor_id": supervisor.id,
        }


def test_history_filters_by_plate_status_dates_location_camera_and_creator(auth_client, app):
    ids = _seed_history_rows(app)

    resp = auth_client.get(
        "/history?"
        "plate=ABC&status=unsafe&date_from=2026-06-01&date_to=2026-06-01&"
        "location=North&camera=CAM-A&created_by="
        f"{ids['operator_id']}"
    )

    assert resp.status_code == 200
    assert b"ABC-123" in resp.data
    assert b"XYZ-999" not in resp.data
    assert b"DUP-222" not in resp.data
    assert b"1 found" in resp.data


def test_history_filters_by_normalized_defect(auth_client, app):
    _seed_history_rows(app)

    resp = auth_client.get("/history?defect=Bulge")

    assert resp.status_code == 200
    assert b"DUP-222" in resp.data
    assert b"ABC-123" not in resp.data


def test_history_filters_duplicate_uploads(auth_client, app):
    _seed_history_rows(app)

    resp = auth_client.get("/history?duplicates=only")

    assert resp.status_code == 200
    assert b"ABC-123" in resp.data
    assert b"DUP-222" in resp.data
    assert b"XYZ-999" not in resp.data


def test_history_location_camera_filters_match_operational_catalog(auth_client, app):
    with app.app_context():
        location = Location(name="Normalized Plaza", normalized_name="normalized plaza", zone="Zone 7")
        camera = Camera(name="CAM-Z7", normalized_name="cam-z7", location=location, zone="Zone 7")
        db.session.add_all([location, camera])
        db.session.flush()
        db.session.add(
            Inspection(
                timestamp=datetime(2026, 7, 1, 9),
                plate="ZONE-7",
                location="Legacy Label",
                camera="Legacy Camera",
                location_id=location.id,
                camera_id=camera.id,
                status="safe",
                confidence=90,
            )
        )
        db.session.commit()

    resp = auth_client.get("/history?location=normalized&camera=CAM-Z7")

    assert resp.status_code == 200
    assert b"ZONE-7" in resp.data
    assert b"Zone 7" in resp.data


def test_user_can_save_and_delete_history_filter(auth_client, app):
    resp = auth_client.post(
        "/history/saved-filters",
        data={"name": "Unsafe North", "status": "unsafe", "location": "North Gate"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        saved = SavedFilter.query.filter_by(name="Unsafe North").one()
        assert saved.params_dict == {"location": "North Gate", "status": "unsafe"}
        saved_id = saved.id

    page = auth_client.get("/history")
    assert b"Unsafe North" in page.data

    delete = auth_client.post(f"/history/saved-filters/{saved_id}/delete", follow_redirects=False)
    assert delete.status_code in (302, 303)
    with app.app_context():
        assert SavedFilter.query.filter_by(id=saved_id).first() is None
