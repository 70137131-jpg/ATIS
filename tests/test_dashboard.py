"""Dashboard metric tests."""

from datetime import datetime, timedelta

from models import Alert, Inspection, db


def test_dashboard_uses_today_counts_and_real_average_processing(auth_client, app):
    today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    with app.app_context():
        today_safe = Inspection(
            timestamp=today,
            location="Today Gate",
            status="safe",
            confidence=91,
            inference_ms=120,
        )
        today_unsafe = Inspection(
            timestamp=today + timedelta(hours=1),
            location="Today Gate",
            status="unsafe",
            confidence=72,
            inference_ms=180,
        )
        old_safe = Inspection(
            timestamp=yesterday,
            location="Old Gate",
            status="safe",
            confidence=99,
            inference_ms=900,
        )
        db.session.add_all([today_safe, today_unsafe, old_safe])
        db.session.flush()
        db.session.add(Alert(inspection_id=today_unsafe.id, status="pending"))
        db.session.commit()

    resp = auth_client.get("/dashboard")

    assert resp.status_code == 200
    assert b"2</div>" in resp.data
    assert b"3 all-time inspections" in resp.data
    assert b"50.0% pass rate" in resp.data
    assert b"150ms" in resp.data
    assert b"1 pending alerts" in resp.data
