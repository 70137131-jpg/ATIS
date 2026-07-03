"""Model feedback export tests."""

from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

from models import AuditEvent, Inspection, User, db


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


def test_model_feedback_export_zip_contains_manifest_and_corrected_images(client, app):
    reviewer_id = _auth_as(client, app, "feedback-export@example.com", "Supervisor")
    with app.app_context():
        included = Inspection(
            timestamp=datetime(2026, 2, 3, 9),
            location="Feedback Gate",
            camera="CAM-FB",
            status="unsafe",
            confidence=82,
            defects="Cracking",
            image_data=b"fake-image-bytes",
            image_mime="image/jpeg",
            image_storage="db",
            image_size=16,
            review_status="false_positive",
            correction_label="normal",
            reviewer_id=reviewer_id,
            reviewed_at=datetime(2026, 2, 4, 10),
            predicted_class="cracked",
            model_version="modelabc",
            model_threshold=60,
            inference_ms=123,
        )
        missing_image = Inspection(
            timestamp=datetime(2026, 2, 3, 10),
            location="Feedback Gate",
            status="unsafe",
            confidence=70,
            review_status="false_negative",
            correction_label="cracked",
            reviewer_id=reviewer_id,
            reviewed_at=datetime(2026, 2, 4, 11),
        )
        no_correction = Inspection(
            timestamp=datetime(2026, 2, 3, 11),
            location="Feedback Gate",
            status="safe",
            confidence=95,
            image_data=b"not-included",
            image_mime="image/jpeg",
            image_storage="db",
            review_status="approved",
        )
        db.session.add_all([included, missing_image, no_correction])
        db.session.commit()
        included_id = included.id

    resp = client.get("/api/model-feedback/export?from=2026-02-01&to=2026-02-28")

    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    with ZipFile(BytesIO(resp.data)) as archive:
        names = set(archive.namelist())
        image_name = f"images/normal/inspection_{included_id}.jpg"
        assert "manifest.csv" in names
        assert "README.txt" in names
        assert image_name in names
        assert archive.read(image_name) == b"fake-image-bytes"
        manifest = archive.read("manifest.csv").decode("utf-8-sig")
        assert "inspection_id,image_path,label,review_status" in manifest
        assert f"{included_id},{image_name},normal,false_positive" in manifest
        assert "modelabc" in manifest
        assert "cracked" in manifest

    with app.app_context():
        event = AuditEvent.query.filter_by(action="model_feedback.exported").one()
        assert event.entity_type == "model_feedback"
        assert event.details_dict["total_matches"] == 2
        assert event.details_dict["exported_rows"] == 1
        assert event.details_dict["skipped_missing_image"] == 1


def test_model_feedback_export_requires_report_role(client, app):
    _auth_as(client, app, "operator-feedback@example.com", "Operator")

    resp = client.get("/api/model-feedback/export?from=2026-02-01&to=2026-02-28")

    assert resp.status_code == 403
