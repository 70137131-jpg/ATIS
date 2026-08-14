"""Inspection upload -> prediction -> alert / image-persistence tests.

The YOLO classifier is monkeypatched so these exercise the route logic (DB
writes, alert creation, durable image storage) without loading the model.
"""

from models import Alert, Camera, DefectType, Inspection, InspectionDefect, Location, db
from routes import inspections as inspection_routes
from routes import live as live_routes
from services.anpr import PlateReadResult

from conftest import make_jpeg


def _fake_prediction(status, defects):
    boxes = []
    if status == "unsafe" and defects:
        boxes = [{
            "label": defects[0],
            "confidence": 93,
            "severity": "High",
            "bbox": [0.1, 0.1, 0.5, 0.5],
        }]
    return {
        "status": status,
        "confidence": 93,
        "defects": defects,
        "predicted_class": "crack" if status == "unsafe" else "normal",
        "threshold": 35,
        "low_confidence": False,
        "boxes": boxes,
        "bounding_boxes": boxes,
        "model_path": "test",
    }


def _post_predict(client, monkeypatch, tmp_path, status="safe", defects=None):
    client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes, "classify_tyre_image",
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
    assert body["model_threshold"] == 35
    assert body["inference_ms"] >= 0

    with app.app_context():
        insp = db.session.get(Inspection, body["inspection_id"])
        assert insp is not None
        assert insp.location == "Test Gate"
        # Image bytes are persisted in the DB (survive container rebuilds).
        assert insp.image_data is not None and len(insp.image_data) > 0
        assert insp.image_mime == "image/jpeg"
        assert insp.image_storage == "db"
        assert insp.image_size == len(insp.image_data)
        assert insp.created_by.email == "admin@atis.com"
        assert insp.image_checksum and len(insp.image_checksum) == 64
        assert insp.predicted_class == "normal"
        assert insp.model_path == "test"
        assert insp.model_threshold == 35
        assert insp.low_confidence is False
        assert insp.inference_ms is not None and insp.inference_ms >= 0
        # A "safe" result must not raise an alert.
        assert Alert.query.filter_by(inspection_id=insp.id).count() == 0


def test_predict_normalizes_metadata(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )

    resp = auth_client.post(
        "/predict",
        data={
            "image": (make_jpeg(), "tyre.jpg"),
            "plate": " abc 123 ",
            "location": "  North   Gate  ",
            "camera": " cam-01 ",
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    with app.app_context():
        insp = db.session.get(Inspection, resp.get_json()["inspection_id"])
        assert insp.plate == "ABC-123"
        assert insp.plate_source == "manual"
        assert insp.location == "North Gate"
        assert insp.camera == "CAM-01"
        assert insp.location_ref.name == "North Gate"
        assert insp.location_ref.is_active is True
        assert insp.camera_ref.name == "CAM-01"
        assert insp.camera_ref.location_id == insp.location_id


def test_predict_auto_reads_plate_when_plate_is_blank(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )
    monkeypatch.setattr(
        inspection_routes,
        "read_plate_image",
        lambda *_a, **_k: PlateReadResult(
            plate="ABC-1234",
            confidence=87,
            raw_text="ABC 1234",
            source="tesseract",
        ),
    )

    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["plate"] == "ABC-1234"
    assert body["plate_source"] == "tesseract"
    assert body["plate_confidence"] == 87
    assert body["plate_raw_text"] == "ABC 1234"
    with app.app_context():
        insp = db.session.get(Inspection, body["inspection_id"])
        assert insp.plate == "ABC-1234"
        assert insp.plate_source == "tesseract"
        assert insp.plate_confidence == 87
        assert insp.plate_raw_text == "ABC 1234"


def test_predict_keeps_low_confidence_plate_for_review(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )
    monkeypatch.setattr(
        inspection_routes,
        "read_plate_image",
        lambda *_a, **_k: PlateReadResult(
            plate="LOW-123",
            confidence=40,
            raw_text="LOW 123",
            source="tesseract",
        ),
    )

    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["plate"] is None
    assert body["plate_source"] == "tesseract_low_confidence"
    assert body["plate_confidence"] == 40
    assert "candidate: LOW-123" in body["plate_raw_text"]
    with app.app_context():
        insp = db.session.get(Inspection, body["inspection_id"])
        assert insp.plate is None
        assert insp.plate_source == "tesseract_low_confidence"


def test_anpr_preview_returns_plate(auth_client, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "read_plate_image",
        lambda *_a, **_k: PlateReadResult(
            plate="LEA-4455",
            confidence=91,
            raw_text="LEA 4455",
            source="tesseract",
        ),
    )

    resp = auth_client.post(
        "/api/anpr/preview",
        data={"image": (make_jpeg(), "plate.jpg")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "plate": "LEA-4455",
        "confidence": 91,
        "raw_text": "LEA 4455",
        "source": "tesseract",
        "needs_review": False,
        "min_confidence": 55,
    }


def test_anpr_preview_flags_low_confidence_plate(auth_client, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "read_plate_image",
        lambda *_a, **_k: PlateReadResult(
            plate="LOW-123",
            confidence=40,
            raw_text="LOW 123",
            source="tesseract",
        ),
    )

    resp = auth_client.post(
        "/api/anpr/preview",
        data={"image": (make_jpeg(), "plate.jpg")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["plate"] == "LOW-123"
    assert body["needs_review"] is True
    assert body["min_confidence"] == 55


def test_predict_reuses_operational_location_and_camera(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )

    for filename in ("first.jpg", "second.jpg"):
        resp = auth_client.post(
            "/predict",
            data={
                "image": (make_jpeg(), filename),
                "location": "North Gate",
                "camera": "CAM-01",
            },
            content_type="multipart/form-data",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200

    with app.app_context():
        assert Location.query.filter_by(normalized_name="north gate").count() == 1
        assert Camera.query.filter_by(normalized_name="cam-01").count() == 1


def test_predict_reports_duplicate_checksum(auth_client, app, monkeypatch, tmp_path):
    first = _post_predict(auth_client, monkeypatch, tmp_path, status="safe").get_json()
    second = _post_predict(auth_client, monkeypatch, tmp_path, status="safe").get_json()

    assert second["duplicate_of"] == first["inspection_id"]

    detail = auth_client.get(f"/inspection/{second['inspection_id']}")
    assert detail.status_code == 200
    assert b"Duplicate Uploads" in detail.data
    assert f"/inspection/{second['inspection_id']}/compare/{first['inspection_id']}".encode() in detail.data

    compare = auth_client.get(f"/inspection/{second['inspection_id']}/compare/{first['inspection_id']}")
    assert compare.status_code == 200
    assert b"Duplicate Upload Comparison" in compare.data
    assert b"Primary Inspection" in compare.data
    assert b"Matched Inspection" in compare.data


def test_duplicate_compare_rejects_different_checksums(auth_client, app):
    with app.app_context():
        first = Inspection(
            location="A",
            status="safe",
            confidence=90,
            image_checksum="checksum-a",
            image_data=b"a",
            image_mime="image/jpeg",
        )
        second = Inspection(
            location="B",
            status="safe",
            confidence=90,
            image_checksum="checksum-b",
            image_data=b"b",
            image_mime="image/jpeg",
        )
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id = first.id, second.id

    resp = auth_client.get(f"/inspection/{first_id}/compare/{second_id}")

    assert resp.status_code == 404


def test_predict_rejects_too_long_metadata(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )

    resp = auth_client.post(
        "/predict",
        data={
            "image": (make_jpeg(), "tyre.jpg"),
            "plate": "X" * 21,
            "location": "Gate",
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 400
    assert "Plate" in resp.get_json()["error"]


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


def test_not_tyre_prediction_is_stored_without_alert(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: {
            "status": "unsafe",
            "confidence": 0,
            "defects": ["Not a tyre"],
            "predicted_class": "not_tyre",
            "threshold": 60,
            "low_confidence": False,
            "model_path": "test",
        },
    )

    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "not_tyre.jpg"), "location": "Live Camera"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["predicted_class"] == "not_tyre"
    assert body["defects"] == ["Not a tyre"]

    with app.app_context():
        assert Alert.query.filter_by(inspection_id=body["inspection_id"]).count() == 0


def test_low_confidence_normal_raises_a_review_alert_not_a_defect(
    auth_client, app, monkeypatch, tmp_path
):
    """The alert-fatigue split: a low-confidence normal shares the worklist with
    real defects so nothing is missed, but is tagged `review` so it can be
    counted and filtered apart from an actual crack."""
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: {
            "status": "unsafe",
            "outcome": "needs_review",
            "confidence": 52,
            "defects": ["Low-confidence normal — manual review"],
            "predicted_class": "normal",
            "classifier_class": "normal",
            "threshold": 60,
            "low_confidence": True,
            "model_path": "test",
        },
    )

    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "unsure.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # The binary status is unchanged, so reports and metrics keep their meaning.
    assert body["status"] == "unsafe"
    assert body["outcome"] == "needs_review"

    with app.app_context():
        inspection = db.session.get(Inspection, body["inspection_id"])
        assert inspection.status == "unsafe"
        assert inspection.outcome == "needs_review"

        alerts = Alert.query.filter_by(inspection_id=body["inspection_id"]).all()
        assert len(alerts) == 1
        assert alerts[0].kind == "review"


def test_cracked_prediction_raises_a_defect_alert(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(
        auth_client, monkeypatch, tmp_path, status="unsafe", defects=["Cracking"]
    )
    body = resp.get_json()

    with app.app_context():
        inspection = db.session.get(Inspection, body["inspection_id"])
        assert inspection.outcome == "unsafe"
        alerts = Alert.query.filter_by(inspection_id=body["inspection_id"]).all()
        assert len(alerts) == 1
        assert alerts[0].kind == "defect"


def test_gate_overriding_a_cracked_call_still_raises_an_alert(
    auth_client, app, monkeypatch, tmp_path
):
    """A not-tyre verdict that overrode a 'cracked' classifier call is a conflict.

    It could be a genuinely cracked tyre the gate misjudged (a dark or
    low-contrast photo), so it must not be dropped the way a plain not-tyre
    frame is — otherwise the gate becomes a source of missed defects.
    """
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: {
            "status": "unsafe",
            # The gate keeps a defect outcome when it overrides a cracked call.
            "outcome": "unsafe",
            "confidence": 0,
            "defects": ["Not a tyre"],
            "predicted_class": "not_tyre",
            "classifier_class": "cracked",
            "threshold": 60,
            "low_confidence": False,
            "model_path": "test",
        },
    )

    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "conflict.jpg"), "location": "Live Camera"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["predicted_class"] == "not_tyre"

    with app.app_context():
        alerts = Alert.query.filter_by(inspection_id=body["inspection_id"]).all()
        assert len(alerts) == 1
        assert alerts[0].status == "pending"
        # It is real defect work, not a review item, despite the not_tyre class.
        assert alerts[0].kind == "defect"


def test_unsafe_prediction_persists_and_renders_boxes(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(
        auth_client, monkeypatch, tmp_path, status="unsafe", defects=["Crack"]
    )
    body = resp.get_json()
    inspection_id = body["inspection_id"]

    # Boxes returned in the JSON response for the immediate overlay...
    assert body["bounding_boxes"][0]["label"] == "Crack"

    # ...and persisted so the detail page can redraw them.
    with app.app_context():
        insp = db.session.get(Inspection, inspection_id)
        assert insp.box_list and insp.box_list[0]["bbox"] == [0.1, 0.1, 0.5, 0.5]
        defect_type = DefectType.query.filter_by(normalized_name="crack").one()
        defect = InspectionDefect.query.filter_by(
            inspection_id=inspection_id,
            defect_type_id=defect_type.id,
        ).one()
        assert defect.severity == "High"
        assert defect.confidence == 93
        assert defect.bbox_list == [0.1, 0.1, 0.5, 0.5]
        assert defect.model_source == "test"
        assert insp.defect_list == ["Crack"]

    detail = auth_client.get(f"/inspection/{inspection_id}")
    assert detail.status_code == 200
    assert b"insp-boxes-data" in detail.data


def test_media_route_serves_stored_image(auth_client, app, monkeypatch, tmp_path):
    resp = _post_predict(auth_client, monkeypatch, tmp_path, status="safe")
    inspection_id = resp.get_json()["inspection_id"]

    img = auth_client.get(f"/media/inspection/{inspection_id}")
    assert img.status_code == 200
    assert img.mimetype == "image/jpeg"
    assert len(img.data) > 0


def test_media_route_serves_object_storage_image(auth_client, app, monkeypatch):
    with app.app_context():
        insp = Inspection(
            location="Object Store Gate",
            status="safe",
            confidence=91,
            image_storage="s3",
            image_object_key="inspection-images/test.jpg",
            image_mime="image/jpeg",
            image_size=9,
        )
        db.session.add(insp)
        db.session.commit()
        inspection_id = insp.id

    monkeypatch.setattr(
        inspection_routes,
        "load_image",
        lambda inspection: (b"object-bytes", inspection.image_mime),
    )

    img = auth_client.get(f"/media/inspection/{inspection_id}")

    assert img.status_code == 200
    assert img.mimetype == "image/jpeg"
    assert img.data == b"object-bytes"


def test_live_capture_is_stored_and_rendered_on_dashboard(auth_client, app, monkeypatch, tmp_path):
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes,
        "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )

    resp = auth_client.post(
        "/predict",
        data={
            "image": (make_jpeg(), "live_capture.jpg"),
            "location": "Live Camera",
            "camera": "LIVE-CAM",
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["dashboard_url"] == "/dashboard"
    assert body["inference_ms"] >= 0

    with app.app_context():
        insp = db.session.get(Inspection, body["inspection_id"])
        assert insp.location == "Live Camera"
        assert insp.camera == "LIVE-CAM"
        assert insp.image_data is not None and len(insp.image_data) > 0
        assert insp.inference_ms is not None

    dashboard = auth_client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"Live Camera" in dashboard.data
    assert b"LIVE-CAM" in dashboard.data
    assert f"/media/inspection/{body['inspection_id']}".encode() in dashboard.data


def test_live_analyze_classifies_a_frame(auth_client, app, monkeypatch):
    """The browser-camera endpoint decodes a posted JPEG and returns a result."""
    monkeypatch.setattr(
        live_routes, "classify_tyre_frame",
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
    # The endpoint passes inference boxes straight through.
    assert body["boxes"] == [
        {
            "label": "Cracking",
            "confidence": 93,
            "severity": "High",
            "bbox": [0.1, 0.1, 0.5, 0.5],
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
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
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


def test_predict_removes_upload_when_inference_fails(auth_client, app, monkeypatch, tmp_path):
    """A failed inference must not leave the saved upload behind on disk."""
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)

    def _boom(*_a, **_k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(inspection_routes, "classify_tyre_image", _boom)
    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302  # redirected back to the form with a flash
    assert list(tmp_path.iterdir()) == []
    with app.app_context():
        assert Inspection.query.count() == 0


def test_predict_removes_upload_when_storage_fails(auth_client, app, monkeypatch, tmp_path):
    """A failed image-storage backend must not leave the saved upload behind."""
    auth_client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes, "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction("safe", []),
    )

    def _storage_down(*_a, **_k):
        raise RuntimeError("bucket unavailable")

    monkeypatch.setattr(inspection_routes, "store_image", _storage_down)
    resp = auth_client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Test Gate"},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert list(tmp_path.iterdir()) == []
    with app.app_context():
        assert Inspection.query.count() == 0
