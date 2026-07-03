"""Pytest fixtures for the ATIS dashboard.

``app.py`` builds the Flask app at import time, so we point it at a throwaway
SQLite file and disable CSRF/model-warmup *before* importing it.
"""

import os
import tempfile
from io import BytesIO

import pytest

# --- Configure the environment BEFORE importing the app module ---------------
_db_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["ATIS_ENV"] = "development"          # dev config (no https-only cookies)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["ATIS_WARMUP"] = "0"                 # don't load the YOLO model in tests

import app as atis_app  # noqa: E402
from models import db, User  # noqa: E402

atis_app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
# The whole suite runs in seconds from one client IP, so per-minute rate limits
# on /login, /predict, etc. would trip mid-run. Disable limiting under test.
atis_app.limiter.enabled = False


@pytest.fixture()
def app():
    """A clean app+DB per test, seeded with one admin user."""
    with atis_app.app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(email="admin@atis.com", role="Admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        yield atis_app.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client):
    """A test client with an authenticated admin session."""
    with client.session_transaction() as sess:
        sess["user"] = "admin@atis.com"
        sess["role"] = "Admin"
    return client


def make_jpeg(size=(16, 16)):
    """Return a BytesIO holding a small, valid JPEG (passes PIL verification)."""
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, (120, 120, 120)).save(buf, format="JPEG")
    buf.seek(0)
    return buf
