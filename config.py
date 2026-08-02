"""
config.py — Centralised, environment-driven configuration for ATIS.

All runtime configuration is read from environment variables here so the rest of
the app has a single source of truth. ``Config.validate()`` fails fast on insecure
production settings (e.g. a missing or default SECRET_KEY) instead of silently
booting an unsafe server.

Environment selection:
    ATIS_ENV (or FLASK_ENV) = "development" (default) | "production"

In production the app refuses to start unless a strong SECRET_KEY is provided.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# The insecure placeholder the project shipped with. Never allowed in production.
DEFAULT_INSECURE_SECRET = "atis-secret-key-change-in-production"


def _env_bool(name, default=False):
    """Read a boolean environment variable (1/true/yes/on -> True)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def get_database_url():
    """Return the configured database URL, defaulting to local SQLite.

    Rewrites legacy ``postgres://`` URLs to ``postgresql://`` for psycopg2.
    """
    default_sqlite = BASE_DIR / "instance" / "atis.db"
    default_sqlite.parent.mkdir(exist_ok=True)
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{default_sqlite}")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


class Config:
    """Application configuration loaded from the environment at import time."""

    ENV_NAME = os.environ.get("ATIS_ENV", os.environ.get("FLASK_ENV", "development")).lower()
    IS_PRODUCTION = ENV_NAME in {"production", "prod"}

    # Debug is OFF unless explicitly enabled, even in development.
    DEBUG = _env_bool("FLASK_DEBUG", False)

    # In production there is no fallback secret — validate() enforces this.
    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "" if IS_PRODUCTION else DEFAULT_INSECURE_SECRET
    )

    # Database
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = (
        {} if SQLALCHEMY_DATABASE_URI.startswith("sqlite") else {"pool_pre_ping": True}
    )

    # Uploads — cap request size so oversized files are rejected with a 413.
    MAX_CONTENT_LENGTH = int(float(os.environ.get("ATIS_MAX_UPLOAD_MB", "10")) * 1024 * 1024)

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    # Only require HTTPS-only cookies in production (dev runs over plain http).
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    # In production the app is often embedded in a cross-site iframe (e.g. Hugging
    # Face Spaces). A "Lax" cookie is dropped in that context, which loses the
    # session and breaks CSRF ("session token is missing"). "None" (which requires
    # Secure=True, satisfied in production) lets the session survive the iframe.
    # Dev stays "Lax" because "None" without Secure is rejected over plain http.
    SESSION_COOKIE_SAMESITE = "None" if IS_PRODUCTION else "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("ATIS_SESSION_HOURS", "8")))

    # Rate limiting storage (in-memory by default; use Redis for multi-worker prod).
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Data retention (PII / personal data governance). Inspections store plates
    # and images; audit events store IP addresses. Both are personal data, so a
    # deployment must be able to age them out. 0 (the default) means "retain
    # forever" — retention is OFF until an operator sets a policy, because
    # silently deleting highway-safety records would itself be unsafe. The purge
    # is applied by the `flask atis-purge-expired` command (run it from cron).
    RETENTION_DAYS = int(os.environ.get("ATIS_RETENTION_DAYS", "0"))
    AUDIT_RETENTION_DAYS = int(os.environ.get("ATIS_AUDIT_RETENTION_DAYS", "0"))

    # Async (background) inference. When on, /predict returns a job id immediately
    # and a bounded in-process worker pool runs the slow model call off the
    # request path. No external broker/worker — fits the single-container default.
    ASYNC_INFERENCE = _env_bool("ATIS_ASYNC_INFERENCE", False)
    INFERENCE_WORKERS = max(1, int(os.environ.get("ATIS_INFERENCE_WORKERS", "1")))
    # Run jobs inline instead of on the pool (deterministic tests / debugging).
    INFERENCE_SYNC_JOBS = _env_bool("ATIS_INFERENCE_SYNC_JOBS", False)

    # Short-TTL in-process cache for expensive dashboard/report aggregations.
    # 0 (default) disables caching, so results are always live. A small value
    # (e.g. 30) bounds staleness while cutting repeated aggregate recomputation.
    STATS_CACHE_SECONDS = int(os.environ.get("ATIS_STATS_CACHE_SECONDS", "0"))

    # Behaviour flags — demo conveniences are disabled in production by default.
    SEED_DEMO_DATA = _env_bool("ATIS_SEED_DEMO", not IS_PRODUCTION)
    ENABLE_DEMO_LOGIN_ALIASES = _env_bool("ATIS_DEMO_ALIASES", not IS_PRODUCTION)
    # The login page prints the well-known README demo credentials. Never show
    # them on a production host (they read like a backdoor, and production demo
    # accounts use ATIS_DEMO_PASSWORD anyway, so the printed password is wrong).
    SHOW_DEMO_CREDENTIALS = _env_bool("ATIS_SHOW_DEMO_CREDENTIALS", not IS_PRODUCTION)

    @classmethod
    def validate(cls):
        """Refuse to boot with an insecure configuration in production."""
        if cls.IS_PRODUCTION and (
            not cls.SECRET_KEY or cls.SECRET_KEY == DEFAULT_INSECURE_SECRET
        ):
            raise RuntimeError(
                "SECRET_KEY must be set to a strong, unique value when "
                "ATIS_ENV=production. Refusing to start with a missing or default "
                "secret key. Generate one with: "
                "python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
