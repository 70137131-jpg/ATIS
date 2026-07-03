"""Authentication / access-control tests."""

from models import User, db


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


def test_healthz_is_public(client):
    """The liveness probe must answer without a session (container health checks)."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"password" in resp.data.lower()


def test_valid_login_grants_access(client):
    resp = client.post(
        "/login",
        data={"email": "admin@atis.com", "password": "admin123"},
        follow_redirects=False,
    )
    # Successful login redirects away from /login...
    assert resp.status_code in (302, 303)
    # ...and a protected page is now reachable without a redirect to login.
    dash = client.get("/dashboard")
    assert dash.status_code == 200


def test_invalid_login_is_rejected(client):
    client.post(
        "/login",
        data={"email": "admin@atis.com", "password": "wrong-password"},
        follow_redirects=False,
    )
    # Not authenticated -> protected page bounces to login.
    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code in (301, 302)
    assert "/login" in dash.headers.get("Location", "")


def test_protected_route_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_logout_clears_session(auth_client):
    assert auth_client.get("/dashboard").status_code == 200
    auth_client.get("/logout")
    after = auth_client.get("/dashboard", follow_redirects=False)
    assert after.status_code in (301, 302)


def test_operator_cannot_access_reports_or_alert_management(client, app):
    _auth_as(client, app, "operator@example.com", "Operator")

    reports = client.get("/reports", follow_redirects=False)
    alerts = client.get("/alerts", follow_redirects=False)

    assert reports.status_code == 403
    assert alerts.status_code == 403


def test_supervisor_can_access_reports_and_alerts(client, app):
    _auth_as(client, app, "supervisor@example.com", "Supervisor")

    assert client.get("/reports").status_code == 200
    assert client.get("/alerts").status_code == 200


def test_inspector_can_access_inspection_tools(client, app):
    _auth_as(client, app, "inspector@example.com", "Inspector")

    assert client.get("/inspect").status_code == 200
    assert client.get("/live").status_code == 200


def test_report_api_denies_operator_with_json_403(client, app):
    _auth_as(client, app, "operator-json@example.com", "Operator")

    resp = client.get(
        "/api/reports/safety-trend?from=2026-01-01&to=2026-01-02",
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "Forbidden"


def test_operator_nav_hides_alerts_and_reports(client, app):
    _auth_as(client, app, "operator-nav@example.com", "Operator")

    resp = client.get("/dashboard")

    assert resp.status_code == 200
    assert b"/inspect" in resp.data
    assert b"/live" in resp.data
    assert b"/alerts" not in resp.data
    assert b"/reports" not in resp.data


def test_supervisor_nav_hides_inspection_tools(client, app):
    _auth_as(client, app, "supervisor-nav@example.com", "Supervisor")

    resp = client.get("/dashboard")

    assert resp.status_code == 200
    assert b"/alerts" in resp.data
    assert b"/reports" in resp.data
    assert b"/inspect" not in resp.data
    assert b"/live" not in resp.data
