"""Async (background) inference job tests."""

import time

from models import Alert, InferenceJob, Inspection, User, db
from routes import inspections as inspection_routes
from services import inference_jobs

from conftest import make_jpeg


def _fake_prediction(status, defects):
    boxes = []
    if status == "unsafe" and defects:
        boxes = [{"label": defects[0], "confidence": 93, "severity": "High", "bbox": [0.1, 0.1, 0.5, 0.5]}]
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


def _enable_async(app, monkeypatch, *, sync_jobs):
    # setitem so the shared app config reverts after the test (the app object is a
    # module-level singleton reused across tests).
    monkeypatch.setitem(app.config, "ASYNC_INFERENCE", True)
    monkeypatch.setitem(app.config, "INFERENCE_SYNC_JOBS", sync_jobs)


def _post(client, monkeypatch, tmp_path, status="safe", defects=None):
    client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    monkeypatch.setattr(
        inspection_routes, "classify_tyre_image",
        lambda *_a, **_k: _fake_prediction(status, defects or []),
    )
    return client.post(
        "/predict",
        data={"image": (make_jpeg(), "tyre.jpg"), "location": "Async Gate"},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


def test_async_disabled_by_default_returns_sync_result(auth_client, app, monkeypatch, tmp_path):
    # Default config: /predict stays synchronous (200 with inspection_id).
    resp = _post(auth_client, monkeypatch, tmp_path, status="safe")
    assert resp.status_code == 200
    assert resp.get_json()["inspection_id"]


def test_async_predict_returns_202_and_completes(auth_client, app, monkeypatch, tmp_path):
    _enable_async(app, monkeypatch, sync_jobs=True)  # run the job inline for determinism
    resp = _post(auth_client, monkeypatch, tmp_path, status="unsafe", defects=["Cracking"])

    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] == "queued"
    assert body["job_id"]
    status_url = body["status_url"]

    # In sync-jobs mode the worker already ran, so the job is done.
    status = auth_client.get(status_url)
    assert status.status_code == 200
    payload = status.get_json()
    assert payload["status"] == "done"
    result = payload["result"]
    assert result["status"] == "unsafe"
    assert result["detail_url"]

    with app.app_context():
        insp = db.session.get(Inspection, result["inspection_id"])
        assert insp is not None
        assert insp.status == "unsafe"
        # An unsafe async inspection still raises an alert.
        assert Alert.query.filter_by(inspection_id=insp.id).count() == 1
        job = db.session.get(InferenceJob, body["job_id"])
        assert job.inspection_id == insp.id


def test_job_status_hidden_from_other_users(auth_client, client, app, monkeypatch, tmp_path):
    _enable_async(app, monkeypatch, sync_jobs=True)
    resp = _post(auth_client, monkeypatch, tmp_path, status="safe")
    job_id = resp.get_json()["job_id"]

    # A different, unrelated operator cannot read someone else's job.
    with app.app_context():
        other = User(email="other-op@example.com", role="Operator")
        other.set_password("G0odStr0ngPass!")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    with client.session_transaction() as sess:
        sess["user_id"] = other_id
        sess["user"] = "other-op@example.com"
        sess["role"] = "Operator"

    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_async_predict_runs_on_the_thread_pool(auth_client, app, monkeypatch, tmp_path):
    # Exercise the real executor path (not inline) and wait for completion.
    _enable_async(app, monkeypatch, sync_jobs=False)
    try:
        resp = _post(auth_client, monkeypatch, tmp_path, status="safe")
        assert resp.status_code == 202
        status_url = resp.get_json()["status_url"]

        deadline = time.time() + 10
        payload = None
        while time.time() < deadline:
            payload = auth_client.get(status_url).get_json()
            if payload["status"] in {"done", "error"}:
                break
            time.sleep(0.2)

        assert payload is not None and payload["status"] == "done", payload
        assert payload["result"]["inspection_id"]
    finally:
        inference_jobs.shutdown()
