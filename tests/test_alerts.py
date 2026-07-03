"""Alert workflow tests."""

from models import Alert, AlertComment, AuditEvent, Inspection, User, db


def _create_pending_alert(app):
    with app.app_context():
        inspection = Inspection(
            location="Test Gate",
            status="unsafe",
            confidence=91,
            defects="Cracking",
        )
        db.session.add(inspection)
        db.session.flush()
        alert = Alert(inspection_id=inspection.id, status="pending")
        db.session.add(alert)
        db.session.commit()
        return alert.id


def test_acknowledge_alert_updates_status(auth_client, app):
    alert_id = _create_pending_alert(app)

    resp = auth_client.post(
        f"/alerts/{alert_id}/acknowledge",
        data={"response": "Driver notified"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with app.app_context():
        alert = db.session.get(Alert, alert_id)
        assert alert.status == "acknowledged"
        assert alert.response == "Driver notified"
        assert alert.acknowledged_by.email == "admin@atis.com"
        assert alert.acknowledged_at is not None
        assert alert.resolved_by is None


def test_resolve_alert_updates_status(auth_client, app):
    alert_id = _create_pending_alert(app)

    resp = auth_client.post(
        f"/alerts/{alert_id}/resolve",
        data={"response": "Tyre replaced"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with app.app_context():
        alert = db.session.get(Alert, alert_id)
        assert alert.status == "resolved"
        assert alert.response == "Tyre replaced"
        assert alert.acknowledged_by.email == "admin@atis.com"
        assert alert.acknowledged_at is not None
        assert alert.resolved_by.email == "admin@atis.com"
        assert alert.resolved_at is not None


def test_update_alert_details_sets_priority_assignment_sla_and_history(auth_client, app):
    alert_id = _create_pending_alert(app)
    with app.app_context():
        assignee = User(email="assigned@example.com", role="Supervisor")
        assignee.set_password("password123")
        db.session.add(assignee)
        db.session.commit()
        assignee_id = assignee.id

    resp = auth_client.post(
        f"/alerts/{alert_id}/details",
        data={
            "priority": "critical",
            "severity": "critical",
            "assigned_user_id": str(assignee_id),
            "assigned_team": "Mobile Response",
            "sla_due_at": "2026-07-04T15:30",
            "escalation_status": "escalated",
            "resolution_category": "tyre_replaced",
        },
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        alert = db.session.get(Alert, alert_id)
        assert alert.priority == "critical"
        assert alert.severity == "critical"
        assert alert.assigned_user.email == "assigned@example.com"
        assert alert.assigned_team == "Mobile Response"
        assert alert.sla_due_at is not None
        assert alert.escalation_status == "escalated"
        assert alert.resolution_category == "tyre_replaced"
        assert AlertComment.query.filter_by(alert_id=alert_id, comment_type="workflow").count() == 1
        assert AuditEvent.query.filter_by(action="alert.details_updated").count() == 1


def test_add_alert_comment_persists_visible_history(auth_client, app):
    alert_id = _create_pending_alert(app)

    resp = auth_client.post(
        f"/alerts/{alert_id}/comments",
        data={"body": "Escalated to mobile response unit."},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        comment = AlertComment.query.filter_by(alert_id=alert_id, comment_type="comment").one()
        assert comment.body == "Escalated to mobile response unit."
        assert comment.author.email == "admin@atis.com"
        assert AuditEvent.query.filter_by(action="alert.comment_added").count() == 1


def test_resolve_alert_records_resolution_category_and_history(auth_client, app):
    alert_id = _create_pending_alert(app)

    resp = auth_client.post(
        f"/alerts/{alert_id}/resolve",
        data={"response": "Closed after replacement", "resolution_category": "tyre_replaced"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        alert = db.session.get(Alert, alert_id)
        assert alert.resolution_category == "tyre_replaced"
        history = AlertComment.query.filter_by(alert_id=alert_id, comment_type="workflow").one()
        assert "resolved" in history.body


def test_alert_actions_require_auth(client, app):
    alert_id = _create_pending_alert(app)
    resp = client.post(f"/alerts/{alert_id}/acknowledge", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")
