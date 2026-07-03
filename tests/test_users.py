"""User and account management tests."""

from models import User, db


def _auth_as(client, app, email, role, password="password123"):
    with app.app_context():
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user"] = email
        sess["role"] = role
    return user_id


def test_admin_can_create_and_disable_user(client, app):
    _auth_as(client, app, "admin-users@example.com", "Admin")

    create = client.post(
        "/admin/users",
        data={"email": "operator-new@example.com", "role": "Operator", "password": "newpass123"},
        follow_redirects=False,
    )
    assert create.status_code in (302, 303)

    with app.app_context():
        user = User.query.filter_by(email="operator-new@example.com").one()
        assert user.role == "Operator"
        user_id = user.id

    disable = client.post(f"/admin/users/{user_id}/disable", follow_redirects=False)
    assert disable.status_code in (302, 303)

    with app.app_context():
        assert not db.session.get(User, user_id).is_active

    client.get("/logout")
    login = client.post(
        "/login",
        data={"email": "operator-new@example.com", "password": "newpass123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    assert client.get("/dashboard", follow_redirects=False).headers["Location"].endswith("/login")


def test_operator_cannot_manage_users(client, app):
    _auth_as(client, app, "operator-users@example.com", "Operator")

    resp = client.get("/admin/users", follow_redirects=False)

    assert resp.status_code == 403


def test_admin_can_change_role_and_reset_password(client, app):
    _auth_as(client, app, "admin-reset@example.com", "Admin")
    with app.app_context():
        user = User(email="inspector-reset@example.com", role="Inspector")
        user.set_password("oldpass123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    role_resp = client.post(
        f"/admin/users/{user_id}/role",
        data={"role": "Supervisor"},
        follow_redirects=False,
    )
    password_resp = client.post(
        f"/admin/users/{user_id}/password",
        data={"password": "newpass123"},
        follow_redirects=False,
    )

    assert role_resp.status_code in (302, 303)
    assert password_resp.status_code in (302, 303)
    with app.app_context():
        updated = db.session.get(User, user_id)
        assert updated.role == "Supervisor"
        assert updated.check_password("newpass123")


def test_user_can_change_own_password(client, app):
    _auth_as(client, app, "self-change@example.com", "Operator", password="oldpass123")

    resp = client.post(
        "/account/password",
        data={
            "current_password": "oldpass123",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        user = User.query.filter_by(email="self-change@example.com").one()
        assert user.check_password("newpass123")
