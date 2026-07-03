"""
NHA - Automated Highway Inspection System
Main Application Setup (Flask)

This file provides the application factory, shared request hooks, CLI commands,
and the legacy module-level ``app`` export used by WSGI servers and tests.
Route handlers live under routes/.
"""

import os
from pathlib import Path

import click
from flask import (
    Flask,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from atis_inference import (
    find_model_path,
    load_classifier,
)
from config import Config
from models import Alert, Inspection, User, db
from routes.alerts import register_routes as register_alert_routes
from routes.audit import register_routes as register_audit_routes
from routes.auth import register_routes as register_auth_routes
from routes.common import (
    ADMIN_ROLES,
    ALERT_MANAGER_ROLES,
    INSPECTION_OPERATOR_ROLES,
    INSPECTION_REVIEWER_ROLES,
    REPORT_VIEWER_ROLES,
    auth_failure_response,
    session_user,
    wants_json_response,
)
from routes.inspections import register_routes as register_inspection_routes
from routes.live import register_routes as register_live_routes
from routes.operations import register_routes as register_operation_routes
from routes.reports import register_routes as register_report_routes
from routes.users import register_routes as register_user_routes

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

try:
    from flask_migrate import Migrate
except ImportError:
    class Migrate:
        def __init__(self, *args, **kwargs):
            pass


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DEMO_USER_CREDENTIALS = [
    ("admin@atis.com", "admin123", "Admin"),
    ("operator@atis.com", "operator123", "Operator"),
    ("operator@nha.gov.pk", "operator123", "Operator"),
    ("supervisor@atis.com", "super123", "Supervisor"),
    ("inspector@atis.com", "inspect123", "Inspector"),
]

UPLOAD_FOLDER = None
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}
MAX_IMAGE_PIXELS = None
LIVE_FRAME_MAX_BYTES = None
LIVE_FRAME_MAX_PIXELS = None
REPORT_EXPORT_MAX_ROWS = None
REPORT_MAX_DAYS = None

csrf = CSRFProtect()
limiter = None
migrate = None


def ensure_demo_users():
    """Create missing demo accounts without overwriting existing passwords."""
    created = 0
    for email, password, role in DEMO_USER_CREDENTIALS:
        if User.query.filter_by(email=email).first():
            continue
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        created += 1

    if created:
        db.session.commit()
        current_app.logger.info("Seeded %s demo user(s).", created)


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def warmup_model(fail_hard: bool = False, flask_app=None) -> bool:
    """Load the classifier and run one dummy inference at boot."""
    target_app = flask_app or current_app
    try:
        import numpy as np

        model = load_classifier()
        model.predict(np.zeros((224, 224, 3), dtype=np.uint8), verbose=False)
        target_app.logger.info("ATIS model warmup complete: %s", find_model_path())
        return True
    except Exception as exc:  # noqa: BLE001 - surface any load/inference failure
        message = f"ATIS model warmup failed: {exc}"
        if fail_hard:
            raise RuntimeError(message) from exc
        target_app.logger.warning(message)
        return False


def _configure_runtime_settings(flask_app):
    """Populate app config values derived from environment and static paths."""
    global UPLOAD_FOLDER
    global MAX_IMAGE_PIXELS
    global LIVE_FRAME_MAX_BYTES
    global LIVE_FRAME_MAX_PIXELS
    global REPORT_EXPORT_MAX_ROWS
    global REPORT_MAX_DAYS

    UPLOAD_FOLDER = os.path.join(flask_app.static_folder, "uploads")
    MAX_IMAGE_PIXELS = int(os.environ.get("ATIS_MAX_IMAGE_PIXELS", "12000000"))
    LIVE_FRAME_MAX_BYTES = int(
        float(os.environ.get("ATIS_LIVE_FRAME_MAX_MB", "2")) * 1024 * 1024
    )
    LIVE_FRAME_MAX_PIXELS = int(os.environ.get("ATIS_LIVE_FRAME_MAX_PIXELS", "2073600"))
    REPORT_EXPORT_MAX_ROWS = int(os.environ.get("ATIS_REPORT_EXPORT_MAX_ROWS", "1000"))
    REPORT_MAX_DAYS = int(os.environ.get("ATIS_REPORT_MAX_DAYS", "366"))

    flask_app.config["REPORT_EXPORT_MAX_ROWS"] = REPORT_EXPORT_MAX_ROWS
    flask_app.config["REPORT_MAX_DAYS"] = REPORT_MAX_DAYS
    flask_app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    flask_app.config["MAX_IMAGE_PIXELS"] = MAX_IMAGE_PIXELS
    flask_app.config["LIVE_FRAME_MAX_BYTES"] = LIVE_FRAME_MAX_BYTES
    flask_app.config["LIVE_FRAME_MAX_PIXELS"] = LIVE_FRAME_MAX_PIXELS


def _configure_sentry(flask_app):
    """Enable optional Sentry telemetry when SENTRY_DSN is configured."""
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if not sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            environment=flask_app.config["ENV_NAME"],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        )
        flask_app.logger.info("Sentry error tracking enabled (%s).", flask_app.config["ENV_NAME"])
    except Exception as exc:  # noqa: BLE001 - never let telemetry break startup
        flask_app.logger.warning("Sentry init skipped: %s", exc)


def create_app(config_object=Config, config_overrides=None):
    """Create and configure a Flask application instance."""
    global csrf
    global limiter
    global migrate

    flask_app = Flask(__name__)
    flask_app.config.from_object(config_object)
    if config_overrides:
        flask_app.config.update(config_overrides)
    if config_object is Config:
        Config.validate()

    if flask_app.config["IS_PRODUCTION"]:
        from werkzeug.middleware.proxy_fix import ProxyFix

        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _configure_sentry(flask_app)
    _configure_runtime_settings(flask_app)

    db.init_app(flask_app)
    migrate = Migrate(flask_app, db)
    csrf = CSRFProtect(flask_app)
    limiter = Limiter(
        get_remote_address,
        app=flask_app,
        storage_uri=flask_app.config["RATELIMIT_STORAGE_URI"],
    )

    register_auth_routes(flask_app, limiter)
    register_alert_routes(flask_app)
    register_audit_routes(flask_app)
    register_inspection_routes(flask_app, limiter)
    register_live_routes(flask_app, limiter)
    register_operation_routes(flask_app)
    register_report_routes(flask_app)
    register_user_routes(flask_app)

    register_health_endpoint(flask_app)
    register_context_processors(flask_app)
    register_request_hooks(flask_app)
    register_cli(flask_app)
    register_error_handlers(flask_app)

    if env_bool("ATIS_WARMUP", False):
        warmup_model(fail_hard=flask_app.config["IS_PRODUCTION"], flask_app=flask_app)

    return flask_app


def register_context_processors(flask_app):
    @flask_app.context_processor
    def inject_nha_status():
        """Expose common NHA header counts and session info to all templates."""
        if "user" not in session:
            return {}
        return {
            "pending_alert_count": Alert.query.filter_by(status="pending").count(),
            "current_user": session.get("user", ""),
            "current_role": session.get("role", ""),
            "can_manage_alerts": session.get("role") in ALERT_MANAGER_ROLES,
            "can_view_reports": session.get("role") in REPORT_VIEWER_ROLES,
            "can_run_inspections": session.get("role") in INSPECTION_OPERATOR_ROLES,
            "can_review_inspections": session.get("role") in INSPECTION_REVIEWER_ROLES,
            "can_manage_users": session.get("role") in ADMIN_ROLES,
            "recent_alerts": (
                Alert.query
                .join(Inspection)
                .order_by(Alert.created_at.desc())
                .limit(5)
                .all()
            ),
        }


PUBLIC_ENDPOINTS = {"login", "static", "healthz"}


def register_health_endpoint(flask_app):
    @flask_app.get("/healthz")
    def healthz():
        """Unauthenticated liveness probe for container/platform health checks.

        Deliberately cheap (no DB, no model): it answers "is the web process
        serving requests", so an outage of a dependency doesn't put the
        container into a restart loop that can't fix it.
        """
        return jsonify({"status": "ok"}), 200


def register_request_hooks(flask_app):
    @flask_app.before_request
    def require_authenticated_session():
        """Global safety net: enforce login on every endpoint except public ones."""
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None
        user = session_user()
        if user is None:
            session.clear()
            return auth_failure_response()
        g.current_user = user
        return None


def register_cli(flask_app):
    @flask_app.cli.command("create-admin")
    @click.option("--email", prompt=True, help="Login email for the account.")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Account password (stored hashed).",
    )
    @click.option("--role", default="Admin", show_default=True, help="Account role.")
    def create_admin(email, password, role):
        """Create or update a user with a securely hashed password."""
        email = email.strip().lower()
        user = User.query.filter_by(email=email).first()
        action = "Updated" if user else "Created"
        if user is None:
            user = User(email=email, role=role)
            db.session.add(user)
        else:
            user.role = role
        user.set_password(password)
        db.session.commit()
        click.echo(f"✓ {action} user {email} ({role}) with a hashed password.")

    @flask_app.cli.command("seed-demo-users")
    def seed_demo_users_command():
        """Create the demo users after migrations have created the schema."""
        ensure_demo_users()
        click.echo("Demo users are present.")


def register_error_handlers(flask_app):
    @flask_app.errorhandler(413)
    def request_entity_too_large(e):
        """Reject uploads that exceed MAX_CONTENT_LENGTH with a clean message."""
        limit_mb = flask_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        message = f"File too large. Maximum upload size is {limit_mb} MB."
        if request.path.startswith("/api/") or wants_json_response():
            return jsonify({"error": message}), 413
        flash(message, "error")
        return redirect(url_for("new_inspection"))

    @flask_app.errorhandler(404)
    def page_not_found(e):
        """Show a custom 404 page when a URL is not found."""
        return render_template("404.html"), 404

    @flask_app.errorhandler(500)
    def internal_error(e):
        """Show a custom 500 page for internal server errors."""
        return render_template("500.html"), 500


def allowed_file(filename):
    """Check if a filename has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


app = create_app()


if __name__ == "__main__":
    warmup_model(fail_hard=False, flask_app=app)
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
