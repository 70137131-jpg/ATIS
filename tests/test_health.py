"""Liveness and readiness probe tests."""


def test_healthz_is_liveness_only(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_readyz_reports_database_ok(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["database"] is True
    assert body["status"] == "ok"


def test_readyz_is_public(client):
    # Reachable without authentication (platform load balancers are unauthenticated).
    assert client.get("/readyz").status_code in (200, 503)


def test_readyz_returns_503_when_database_down(client, app, monkeypatch):
    from models import db

    def _boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db.session, "execute", _boom)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["database"] is False
    assert body["status"] == "unavailable"
