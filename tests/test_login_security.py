"""Account-lockout, session-revocation, and password-policy tests."""

import os

from models import User, db
from services.login_security import is_locked, register_failed_attempt
from services.passwords import validate_password_strength


def _make_user(app, email="lock@example.com", password="G0odStr0ngPass!"):
    with app.app_context():
        user = User(email=email, role="Operator")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def test_password_policy_rejects_weak_and_common():
    assert validate_password_strength("short") is not None
    assert validate_password_strength("password123") is not None  # common
    assert validate_password_strength("aaaaaaaaaaaa") is not None  # no variety
    assert validate_password_strength("G0odStr0ngPass!") is None


def test_password_policy_rejects_username():
    assert validate_password_strength("Alice1234567", email="alice@example.com") is not None


def test_account_locks_after_repeated_failures(app, monkeypatch):
    monkeypatch.setenv("ATIS_MAX_LOGIN_ATTEMPTS", "3")
    user_id = _make_user(app)
    with app.app_context():
        user = db.session.get(User, user_id)
        assert not is_locked(user)
        register_failed_attempt(user)
        register_failed_attempt(user)
        assert not is_locked(user)
        register_failed_attempt(user)  # third trips the lock
        assert is_locked(user)


def test_login_route_locks_and_blocks(client, app, monkeypatch):
    monkeypatch.setenv("ATIS_MAX_LOGIN_ATTEMPTS", "3")
    _make_user(app, email="brute@example.com", password="G0odStr0ngPass!")

    for _ in range(3):
        client.post("/login", data={"email": "brute@example.com", "password": "wrong"}, follow_redirects=False)

    # Even the correct password is refused once locked.
    resp = client.post(
        "/login",
        data={"email": "brute@example.com", "password": "G0odStr0ngPass!"},
        follow_redirects=True,
    )
    assert b"locked" in resp.data.lower()
    with app.app_context():
        assert is_locked(db.session.get(User, User.query.filter_by(email="brute@example.com").one().id))


def test_successful_login_clears_failure_counter(client, app):
    _make_user(app, email="ok@example.com", password="G0odStr0ngPass!")
    client.post("/login", data={"email": "ok@example.com", "password": "wrong"})
    client.post("/login", data={"email": "ok@example.com", "password": "G0odStr0ngPass!"})
    with app.app_context():
        user = User.query.filter_by(email="ok@example.com").one()
        assert user.failed_login_count == 0
        assert user.locked_until is None
        assert user.last_login_at is not None


def test_session_epoch_bump_revokes_session(client, app):
    user_id = _make_user(app, email="revoke@example.com", password="G0odStr0ngPass!")
    client.post("/login", data={"email": "revoke@example.com", "password": "G0odStr0ngPass!"})
    # Authenticated request works.
    assert client.get("/dashboard").status_code == 200

    # Simulate a password reset elsewhere: bump the epoch. The conftest `app`
    # fixture already holds an app context open for the whole test, so mutate on
    # that active session (a nested app_context would get its own session and the
    # reused request context below would not see the change).
    user = db.session.get(User, user_id)
    user.session_epoch += 1
    db.session.commit()

    # The old session cookie now carries a stale epoch and is rejected.
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")
