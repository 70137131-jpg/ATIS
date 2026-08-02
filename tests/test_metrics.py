"""Prometheus /metrics endpoint tests."""

from models import Inspection, db


def test_metrics_exposes_expected_series(client, app):
    with app.app_context():
        db.session.add(Inspection(plate="M-1", location="Gate", status="safe", confidence=90))
        db.session.add(Inspection(plate="M-2", location="Gate", status="unsafe", confidence=70))
        db.session.commit()

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    body = resp.get_data(as_text=True)
    assert "atis_up 1" in body
    assert 'atis_inspections_total{status="safe"}' in body
    assert 'atis_inspections_total{status="unsafe"}' in body
    assert "atis_alerts_pending" in body
    assert 'atis_inference_jobs{status="queued"}' in body


def test_metrics_is_public(client):
    # Reachable without an authenticated session (scrapers are unauthenticated).
    assert client.get("/metrics").status_code == 200


def test_metrics_token_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("ATIS_METRICS_TOKEN", "secret-token")
    # No/invalid token is rejected once a token is configured.
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # Correct token is accepted.
    ok = client.get("/metrics", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200
