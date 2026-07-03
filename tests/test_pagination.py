"""Pagination tests for high-volume list pages."""

from models import Alert, Inspection, db


def _add_inspections(app, count):
    with app.app_context():
        for idx in range(count):
            db.session.add(
                Inspection(
                    plate=f"TST-{idx:04d}",
                    location="Pagination Gate",
                    status="unsafe" if idx % 2 else "safe",
                    confidence=80 + (idx % 10),
                    defects="Cracking" if idx % 2 else None,
                )
            )
        db.session.commit()


def _add_alerts(app, count):
    with app.app_context():
        for idx in range(count):
            inspection = Inspection(
                plate=f"ALT-{idx:04d}",
                location="Alert Gate",
                status="unsafe",
                confidence=90,
                defects="Cracking",
            )
            db.session.add(inspection)
            db.session.flush()
            db.session.add(Alert(inspection_id=inspection.id, status="pending"))
        db.session.commit()


def test_history_uses_server_pagination(auth_client, app):
    _add_inspections(app, 5)

    resp = auth_client.get("/history?per_page=2")

    assert resp.status_code == 200
    assert b"Page 1 of 3" in resp.data
    assert b"page=2" in resp.data


def test_alerts_use_server_pagination(auth_client, app):
    _add_alerts(app, 5)

    resp = auth_client.get("/alerts?per_page=2")

    assert resp.status_code == 200
    assert b"Page 1 of 3" in resp.data
    assert b"page=2" in resp.data
