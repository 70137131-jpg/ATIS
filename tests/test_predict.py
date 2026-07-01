"""Inspection upload -> prediction -> alert / image-persistence tests.

The YOLO classifier is monkeypatched so these exercise the route logic (DB
writes, alert creation, durable image storage) without loading the model.
"""

import app as atis_app
from models import Alert, Inspection, db

from conftest import make_jpeg


def _fake_prediction(status, defects):
    return {
        "status": status,
        "confidence": 93,
        "defects": defects,
        "predicted_class": "cracked" if status == "unsafe" else "normal",
        "threshold": 60,
        "low_confidence": False,
        "model_path": "test",
    }


def _post_predict(client, monkeypatch, tmp_path, status="safe", defects=None):
    monkeypatch.setattr(atis_app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(
        atis_app, "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction(status, defects or []),
    )
    return client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},  # ask for JSON
    )


def test_predict_creates_inspection_and_stores_image(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(auth_client, monkeypatch, tmp_path, status="safe")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "safe"

    with app.app_context():
        insp = db.session.get(Inspection, body["inspection_id"])
        assert insp is not None
        assert insp.location == "Test Gate"
        # Image bytes are persisted in the DB (survive container rebuilds).
        assert insp.image_data is not None and len(insp.image_data) > 0
        assert insp.image_mime == "image/jpeg"
        # A "safe" result must not raise an alert.
        assert Alert.query.filter_by(inspection_id=insp.id).count() == 0


def test_unsafe_prediction_creates_pending_alert(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(
        auth_client, monkeypatch, tmp_path, status="unsafe", defects=["Cracking"]
    )
    body = resp.get_json()
    assert body["status"] == "unsafe"

    with app.app_context():
        alerts = Alert.query.filter_by(inspection_id=body["inspection_id"]).all()
        assert len(alerts) == 1
        assert alerts[0].status == "pending"


def test_media_route_serves_stored_image(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(auth_client, monkeypatch, tmp_path, status="safe")
    inspection_id = resp.get_json()["inspection_id"]

    img = auth_client.get(f"/media/inspection/{inspection_id}")
    assert img.status_code == 200
    assert img.mimetype == "image/jpeg"
    assert len(img.data) > 0


def test_live_analyze_classifies_a_frame(auth_client, app, monkeypatch):
    """The browser-camera endpoint decodes a posted JPEG and returns a result."""
    monkeypatch.setattr(
        atis_app, "classify_tyre_frame",
        lambda *_a, **_k: _fake_prediction("unsafe", ["Cracking"]),
    )
    resp = auth_client.post(
        "/api/live/analyze",
        data={"frame": (make_jpeg(), "frame.jpg")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "unsafe"
    assert "Cracking" in body["defects"]
    assert body["boxes"] == [
        {
            "label": "cracked",
            "confidence": 93,
            "status": "unsafe",
            "bbox": [0, 0, 1, 1],
        }
    ]


def test_live_analyze_requires_auth(client):
    resp = client.post(
        "/api/live/analyze",
        data={"frame": (make_jpeg(), "frame.jpg")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    # Either the endpoint's own 401 or the app-wide login redirect — never a result.
    assert resp.status_code in (302, 401)


def test_predict_rejects_non_image(auth_client, app, monkeypatch, tmp_path):
    monkeypatch.setattr(atis_app, "UPLOAD_FOLDER", str(tmp_path))
    from io import BytesIO

    resp = auth_client.post(
        "/predict",
        data={"image": (BytesIO(b"not really an image"), "fake.jpg"), "location": "X"},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    # Bad upload should not create an inspection row.
    with app.app_context():
        assert Inspection.query.count() == 0
