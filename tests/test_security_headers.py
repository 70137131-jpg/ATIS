"""Security response-header tests."""


def test_core_security_headers_present(client):
    resp = client.get("/login")
    assert "Content-Security-Policy" in resp.headers
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "object-src 'none'" in csp
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Referrer-Policy" in resp.headers
    assert "Permissions-Policy" in resp.headers


def test_request_id_is_echoed(client):
    resp = client.get("/login")
    assert resp.headers.get("X-Request-ID")


def test_inbound_request_id_is_honoured(client):
    resp = client.get("/login", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.headers.get("X-Request-ID") == "trace-abc-123"


def test_hsts_absent_in_development(client):
    # Dev serves plain http; HSTS is production-only.
    resp = client.get("/login")
    assert "Strict-Transport-Security" not in resp.headers
