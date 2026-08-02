"""Accessibility (WCAG) attribute smoke tests on rendered pages."""

from models import Alert, Inspection, User, db


def _auth_admin(client, app):
    with app.app_context():
        if not User.query.filter_by(email="a11y-admin@example.com").first():
            u = User(email="a11y-admin@example.com", role="Admin")
            u.set_password("G0odStr0ngPass!")
            db.session.add(u)
            db.session.commit()
    with client.session_transaction() as sess:
        sess["user"] = "a11y-admin@example.com"
        sess["role"] = "Admin"
        with app.app_context():
            sess["user_id"] = User.query.filter_by(email="a11y-admin@example.com").first().id


def test_base_layout_has_skip_link_and_main_landmark(client, app):
    _auth_admin(client, app)
    body = client.get("/dashboard").get_data(as_text=True)
    assert 'class="skip-link"' in body
    assert 'href="#main-content"' in body
    assert 'id="main-content"' in body


def test_active_nav_item_marks_aria_current(client, app):
    _auth_admin(client, app)
    body = client.get("/dashboard").get_data(as_text=True)
    # The dashboard link is the current page.
    assert 'aria-current="page"' in body


def test_decorative_icons_are_hidden_from_screen_readers(client, app):
    _auth_admin(client, app)
    body = client.get("/dashboard").get_data(as_text=True)
    assert 'aria-hidden="true"' in body  # from the icon macro


def test_table_headers_have_scope(client, app):
    _auth_admin(client, app)
    with app.app_context():
        db.session.add(Inspection(plate="A11Y-1", location="Gate", status="safe", confidence=90))
        db.session.commit()
    body = client.get("/history").get_data(as_text=True)
    assert '<th scope="col">' in body


def test_flash_region_is_announced(client, app):
    # The login page renders the flash container as a polite live region.
    body = client.get("/login").get_data(as_text=True)
    # Trigger a flash so the container renders.
    resp = client.post("/login", data={"email": "no@one.test", "password": "x"}, follow_redirects=True)
    assert 'role="status"' in resp.get_data(as_text=True)
    assert 'aria-live="polite"' in resp.get_data(as_text=True)
