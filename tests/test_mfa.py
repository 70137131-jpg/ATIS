"""MFA enrolment and second-factor login-flow tests."""

from models import User, db
from services import totp


def _auth(client, app, email="mfa-user@example.com", password="G0odStr0ngPass!"):
    with app.app_context():
        user = User(email=email, role="Operator")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["user"] = email
        sess["role"] = "Operator"
    return uid


def test_enable_mfa_requires_valid_code(client, app):
    uid = _auth(client, app)
    # Prime the setup secret.
    client.get("/account/mfa")
    with client.session_transaction() as sess:
        secret = sess["mfa_setup_secret"]

    # Wrong code does not enable.
    client.post("/account/mfa", data={"action": "enable", "code": "000000"})
    with app.app_context():
        assert db.session.get(User, uid).mfa_enabled is False

    # Correct code enables.
    client.post("/account/mfa", data={"action": "enable", "code": totp.totp_now(secret)})
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.mfa_enabled is True
        assert user.mfa_secret == secret


def test_login_requires_second_factor_when_enabled(client, app):
    email, password = "mfa-login@example.com", "G0odStr0ngPass!"
    with app.app_context():
        user = User(email=email, role="Operator")
        user.set_password(password)
        user.mfa_secret = totp.generate_secret()
        user.mfa_enabled = True
        db.session.add(user)
        db.session.commit()
        secret = user.mfa_secret

    # Correct password alone does not reach the dashboard; it redirects to MFA.
    resp = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/mfa/verify" in resp.headers["Location"]

    # Not yet authenticated: a protected page bounces to login.
    assert client.get("/dashboard", follow_redirects=False).status_code in (301, 302)

    # Wrong code stays on the MFA step.
    bad = client.post("/mfa/verify", data={"code": "000000"}, follow_redirects=False)
    assert "/mfa/verify" in bad.headers["Location"]

    # Correct code completes the login.
    ok = client.post("/mfa/verify", data={"code": totp.totp_now(secret)}, follow_redirects=False)
    assert "/dashboard" in ok.headers["Location"]
    assert client.get("/dashboard").status_code == 200


def test_mfa_verify_without_pending_redirects_to_login(client, app):
    resp = client.get("/mfa/verify", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers["Location"]


def test_disable_mfa_requires_password(client, app):
    uid = _auth(client, app, email="mfa-disable@example.com", password="G0odStr0ngPass!")
    with app.app_context():
        user = db.session.get(User, uid)
        user.mfa_secret = totp.generate_secret()
        user.mfa_enabled = True
        db.session.commit()

    client.post("/account/mfa", data={"action": "disable", "password": "wrong"})
    with app.app_context():
        assert db.session.get(User, uid).mfa_enabled is True

    client.post("/account/mfa", data={"action": "disable", "password": "G0odStr0ngPass!"})
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.mfa_enabled is False
        assert user.mfa_secret is None
