"""Human inspection review workflow tests."""

from models import AuditEvent, Inspection, User, db


def _auth_as(client, app, email, role):
    with app.app_context():
        user = User(email=email, role=role, is_active=True)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user"] = email
        sess["role"] = role
    return user_id


def _create_inspection(app):
    with app.app_context():
        inspection = Inspection(location="Review Gate", status="unsafe", confidence=82)
        db.session.add(inspection)
        db.session.commit()
        return inspection.id


def test_new_inspection_defaults_to_pending_review(app):
    inspection_id = _create_inspection(app)

    with app.app_context():
        inspection = db.session.get(Inspection, inspection_id)
        assert inspection.review_status == "pending_review"
        assert inspection.reviewer is None
        assert inspection.reviewed_at is None
        assert inspection.correction_label is None


def test_reviewer_can_update_review_status_notes_and_correction(client, app):
    reviewer_id = _auth_as(client, app, "reviewer@example.com", "Inspector")
    inspection_id = _create_inspection(app)

    response = client.post(
        f"/inspection/{inspection_id}/review",
        data={
            "review_status": "false_positive",
            "correction_label": "normal",
            "review_notes": "Crack marker was road shadow, not tyre damage.",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    with app.app_context():
        inspection = db.session.get(Inspection, inspection_id)
        assert inspection.review_status == "false_positive"
        assert inspection.correction_label == "normal"
        assert inspection.review_notes == "Crack marker was road shadow, not tyre damage."
        assert inspection.reviewer_id == reviewer_id
        assert inspection.reviewed_at is not None


def test_review_update_logs_audit_event(client, app):
    reviewer_id = _auth_as(client, app, "review-audit@example.com", "Supervisor")
    inspection_id = _create_inspection(app)

    response = client.post(
        f"/inspection/{inspection_id}/review",
        data={
            "review_status": "approved",
            "correction_label": "",
            "review_notes": "Confirmed by supervisor.",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    with app.app_context():
        event = AuditEvent.query.filter_by(action="inspection.reviewed").one()
        assert event.actor_id == reviewer_id
        assert event.entity_type == "inspection"
        assert event.entity_id == inspection_id
        assert event.details_dict["from_status"] == "pending_review"
        assert event.details_dict["to_status"] == "approved"
        assert event.details_dict["to_correction_label"] is None
        assert event.details_dict["has_notes"] is True


def test_operator_cannot_update_review(client, app):
    _auth_as(client, app, "operator-review@example.com", "Operator")
    inspection_id = _create_inspection(app)

    response = client.post(
        f"/inspection/{inspection_id}/review",
        data={"review_status": "approved"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    with app.app_context():
        inspection = db.session.get(Inspection, inspection_id)
        assert inspection.review_status == "pending_review"


def test_invalid_review_status_is_rejected(client, app):
    _auth_as(client, app, "review-invalid@example.com", "Admin")
    inspection_id = _create_inspection(app)

    response = client.post(
        f"/inspection/{inspection_id}/review",
        data={"review_status": "needs_more_magic", "correction_label": "normal"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    with app.app_context():
        inspection = db.session.get(Inspection, inspection_id)
        assert inspection.review_status == "pending_review"
        assert inspection.correction_label is None
        assert AuditEvent.query.filter_by(action="inspection.reviewed").count() == 0


def test_inspection_detail_renders_review_panel(auth_client, app):
    inspection_id = _create_inspection(app)

    response = auth_client.get(f"/inspection/{inspection_id}")

    assert response.status_code == 200
    assert b"Human Review" in response.data
    assert b"Pending Review" in response.data
    assert b"name=\"review_status\"" in response.data


def test_anpr_review_queue_lists_ocr_failures_and_low_confidence(client, app):
    _auth_as(client, app, "anpr-reviewer@example.com", "Inspector")
    with app.app_context():
        missing = Inspection(
            location="Gate A",
            status="safe",
            confidence=91,
            review_status="pending_review",
            plate_source="ocr_failed",
        )
        low_confidence = Inspection(
            location="Gate B",
            status="safe",
            confidence=90,
            review_status="pending_review",
            plate_source="tesseract_low_confidence",
            plate_confidence=40,
            plate_raw_text="LOW 123 | candidate: LOW-123",
        )
        accepted = Inspection(
            location="Gate C",
            status="safe",
            confidence=94,
            review_status="pending_review",
            plate="ABC-1234",
            plate_source="tesseract",
            plate_confidence=88,
        )
        db.session.add_all([missing, low_confidence, accepted])
        db.session.commit()
        missing_id = missing.id
        low_id = low_confidence.id
        accepted_id = accepted.id

    response = client.get("/review/anpr")

    assert response.status_code == 200
    assert b"ANPR Review" in response.data
    assert f"#{missing_id}".encode() in response.data
    assert f"#{low_id}".encode() in response.data
    assert f"#{accepted_id}".encode() not in response.data


def test_operator_cannot_view_anpr_review_queue(client, app):
    _auth_as(client, app, "anpr-operator@example.com", "Operator")

    response = client.get("/review/anpr", follow_redirects=False)

    assert response.status_code == 403
