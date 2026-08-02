"""Audit trail tests."""

from datetime import datetime

from models import Alert, AuditEvent, Inspection, User, db


def _auth_as(client, app, email, role):
    with app.app_context():
        user = User(email=email, role=role)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user"] = email
        sess["role"] = role
    return user_id


def test_report_export_logs_audit_event(client, app):
    actor_id = _auth_as(client, app, "report-audit@example.com", "Supervisor")
    with app.app_context():
        db.session.add(
            Inspection(
                timestamp=datetime(2026, 1, 3, 9),
                location="Audit Gate",
                status="safe",
                confidence=91,
            )
        )
        db.session.commit()

    resp = client.get("/api/reports/export-pdf?from=2026-01-01&to=2026-01-31")

    assert resp.status_code == 200
    with app.app_context():
        event = AuditEvent.query.filter_by(action="report.exported").one()
        assert event.actor_id == actor_id
        assert event.entity_type == "report"
        assert event.details_dict["format"] == "pdf"
        assert event.details_dict["total_matches"] == 1


def test_alert_workflow_logs_audit_events(client, app):
    actor_id = _auth_as(client, app, "alert-audit@example.com", "Supervisor")
    with app.app_context():
        inspection = Inspection(location="Audit Gate", status="unsafe", confidence=70)
        db.session.add(inspection)
        db.session.flush()
        alert = Alert(inspection_id=inspection.id, status="pending")
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    ack = client.post(f"/alerts/{alert_id}/acknowledge", data={"response": "Seen"})
    resolve = client.post(f"/alerts/{alert_id}/resolve", data={"response": "Closed"})

    assert ack.status_code in (302, 303)
    assert resolve.status_code in (302, 303)
    with app.app_context():
        actions = [event.action for event in AuditEvent.query.order_by(AuditEvent.id).all()]
        assert actions == ["alert.acknowledged", "alert.resolved"]
        for event in AuditEvent.query.all():
            assert event.actor_id == actor_id
            assert event.entity_type == "alert"
            assert event.entity_id == alert_id


def test_user_admin_action_logs_audit_event(client, app):
    actor_id = _auth_as(client, app, "user-audit-admin@example.com", "Admin")

    resp = client.post(
        "/admin/users",
        data={"email": "audited-user@example.com", "role": "Operator", "password": "Str0ngPass!2026"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        event = AuditEvent.query.filter_by(action="user.created").one()
        user = User.query.filter_by(email="audited-user@example.com").one()
        assert event.actor_id == actor_id
        assert event.entity_type == "user"
        assert event.entity_id == user.id
        assert event.details_dict["role"] == "Operator"


def test_admin_can_browse_and_filter_audit_events(client, app):
    _auth_as(client, app, "audit-ui-admin@example.com", "Admin")
    with app.app_context():
        db.session.add_all([
            AuditEvent(action="report.exported", actor_email="reporter@example.com", entity_type="report", details="{}"),
            AuditEvent(action="alert.resolved", actor_email="supervisor@example.com", entity_type="alert", details="{}"),
        ])
        db.session.commit()

    resp = client.get("/admin/audit?action=report&entity_type=report")

    assert resp.status_code == 200
    assert b"Audit Log" in resp.data
    assert b"report.exported" in resp.data
    assert b"alert.resolved" not in resp.data


def test_audit_log_requires_admin(client, app):
    _auth_as(client, app, "audit-ui-operator@example.com", "Operator")

    resp = client.get("/admin/audit")

    assert resp.status_code == 403
