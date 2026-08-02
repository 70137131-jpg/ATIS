"""MFA recovery-code tests (unit + login-flow integration)."""

from models import User, db
from services import recovery_codes, totp


class _FakeUser:
    def __init__(self, blob=None):
        self.mfa_recovery_codes = blob


def test_generate_and_hash_roundtrip():
    codes = recovery_codes.generate_codes(5)
    assert len(codes) == 5
    assert all("-" in c for c in codes)
    user = _FakeUser(recovery_codes.hash_codes(codes))
    # A valid code is accepted once, then consumed.
    assert recovery_codes.verify_and_consume(user, codes[0]) is True
    assert recovery_codes.verify_and_consume(user, codes[0]) is False
    assert recovery_codes.remaining_count(user.mfa_recovery_codes) == 4


def test_wrong_code_rejected():
    user = _FakeUser(recovery_codes.hash_codes(recovery_codes.generate_codes(3)))
    assert recovery_codes.verify_and_consume(user, "zzzz-zzzz") is False
    assert recovery_codes.remaining_count(user.mfa_recovery_codes) == 3


def test_enable_generates_recovery_codes_and_shows_once(client, app):
    with app.app_context():
        user = User(email="rec@example.com", role="Operator")
        user.set_password("G0odStr0ngPass!")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["user"] = "rec@example.com"
        sess["role"] = "Operator"

    client.get("/account/mfa")
    with client.session_transaction() as sess:
        secret = sess["mfa_setup_secret"]

    # Enabling returns to the page; the codes are shown once via the session.
    client.post("/account/mfa", data={"action": "enable", "code": totp.totp_now(secret)}, follow_redirects=False)
    page = client.get("/account/mfa")
    body = page.get_data(as_text=True)
    assert "recovery code" in body.lower()

    with app.app_context():
        assert recovery_codes.remaining_count(db.session.get(User, uid).mfa_recovery_codes) == recovery_codes.CODE_COUNT


def test_login_with_recovery_code_consumes_it(client, app):
    email, password = "rec-login@example.com", "G0odStr0ngPass!"
    codes = recovery_codes.generate_codes()
    with app.app_context():
        user = User(email=email, role="Operator")
        user.set_password(password)
        user.mfa_secret = totp.generate_secret()
        user.mfa_enabled = True
        user.mfa_recovery_codes = recovery_codes.hash_codes(codes)
        db.session.add(user)
        db.session.commit()
        uid = user.id

    client.post("/login", data={"email": email, "password": password})
    # A recovery code completes login in place of a TOTP code.
    ok = client.post("/mfa/verify", data={"code": codes[0]}, follow_redirects=False)
    assert "/dashboard" in ok.headers["Location"]
    assert client.get("/dashboard").status_code == 200

    with app.app_context():
        # The used code is consumed (one fewer remaining).
        assert recovery_codes.remaining_count(db.session.get(User, uid).mfa_recovery_codes) == len(codes) - 1
