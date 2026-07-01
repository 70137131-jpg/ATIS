"""Authentication / access-control tests."""


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
