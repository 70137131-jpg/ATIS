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
from sqlalchemy import inspect as inspect_database
from sqlalchemy import text as sql_text
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
from sqlalchemy.orm import joinedload

from atis_inference import (
    find_model_path,
    load_classifier,
)
from config import Config
from models import Alert, User, db
from metrics import register_metrics
from observability import configure_logging
from security import register_security_headers
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
    from flask_migrate import stamp as stamp_migration
except ImportError:
    class Migrate:
        def __init__(self, *args, **kwargs):
            pass

    def stamp_migration(*args, **kwargs):
        raise RuntimeError("Flask-Migrate is required to stamp database revisions.")


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DEMO_USER_CREDENTIALS = [
    ("admin@atis.com", "admin123", "Admin"),
    ("operator@atis.com", "operator123", "Operator"),
    ("operator@nha.gov.pk", "operator123", "Operator"),
    ("supervisor@atis.com", "super123", "Supervisor"),
    ("inspector@atis.com", "inspect123", "Inspector"),
]

# Kept as a module global for live_video_inspection.py; routes read app.config.
UPLOAD_FOLDER = None

csrf = CSRFProtect()
limiter = None
migrate = None


def ensure_demo_users():
    """Create missing demo accounts without overwriting existing passwords.

    The demo passwords are printed in the README, so seeding them verbatim on a
    public production host would be a documented backdoor. In production this
    therefore requires ATIS_DEMO_PASSWORD and gives every demo account that
    password instead of the well-known ones.
    """
    override = os.environ.get("ATIS_DEMO_PASSWORD")
    if current_app.config["IS_PRODUCTION"] and not override:
        current_app.logger.warning(
            "Refusing to seed demo users with well-known README passwords in "
            "production. Set ATIS_DEMO_PASSWORD to seed demo accounts with a "
            "password of your own, or use `flask create-admin`."
        )
        return

    created = 0
    for email, password, role in DEMO_USER_CREDENTIALS:
        if User.query.filter_by(email=email).first():
            continue
        user = User(email=email, role=role)
        user.set_password(override or password)
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

    UPLOAD_FOLDER = os.path.join(flask_app.static_folder, "uploads")
    flask_app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    flask_app.config["MAX_IMAGE_PIXELS"] = int(
        os.environ.get("ATIS_MAX_IMAGE_PIXELS", "12000000")
    )
    flask_app.config["LIVE_FRAME_MAX_BYTES"] = int(
        float(os.environ.get("ATIS_LIVE_FRAME_MAX_MB", "2")) * 1024 * 1024
    )
    flask_app.config["LIVE_FRAME_MAX_PIXELS"] = int(
        os.environ.get("ATIS_LIVE_FRAME_MAX_PIXELS", "2073600")
    )
    flask_app.config["REPORT_EXPORT_MAX_ROWS"] = int(
        os.environ.get("ATIS_REPORT_EXPORT_MAX_ROWS", "1000")
    )
    flask_app.config["REPORT_MAX_DAYS"] = int(os.environ.get("ATIS_REPORT_MAX_DAYS", "366"))


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
    if (
        flask_app.config["IS_PRODUCTION"]
        and flask_app.config["RATELIMIT_STORAGE_URI"].startswith("memory")
        and int(os.environ.get("WEB_CONCURRENCY", "1")) > 1
    ):
        flask_app.logger.warning(
            "Rate limiting uses in-memory storage but WEB_CONCURRENCY > 1: each "
            "gunicorn worker keeps its own counters, so effective limits are "
            "multiplied. Point RATELIMIT_STORAGE_URI at Redis for shared limits."
        )

    _warn_unsafe_production_defaults(flask_app)

    register_auth_routes(flask_app, limiter)
    register_alert_routes(flask_app)
    register_audit_routes(flask_app)
    register_inspection_routes(flask_app, limiter)
    register_live_routes(flask_app, limiter)
    register_operation_routes(flask_app)
    register_report_routes(flask_app)
    register_user_routes(flask_app)

    configure_logging(flask_app)
    register_security_headers(flask_app)
    register_metrics(flask_app)
    register_health_endpoint(flask_app)
    register_context_processors(flask_app)
    register_request_hooks(flask_app)
    register_cli(flask_app)
    register_error_handlers(flask_app)

    if env_bool("ATIS_WARMUP", False):
        warmup_model(fail_hard=flask_app.config["IS_PRODUCTION"], flask_app=flask_app)

    return flask_app


def _warn_unsafe_production_defaults(flask_app):
    """Log loud warnings when production is running on demo-grade data defaults.

    None of these block boot — a demo host legitimately uses them — but on a
    real deployment they mean data loss (ephemeral SQLite), a bloated database
    (image bytes in Postgres), or no way to age out personal data (plates, IPs)
    with no retention policy set. Surfacing them keeps a go-live from silently
    inheriting demo settings.
    """
    if not flask_app.config["IS_PRODUCTION"]:
        return

    if flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        flask_app.logger.warning(
            "Running in production on SQLite. In a container this database is "
            "ephemeral and single-writer; point DATABASE_URL at managed "
            "PostgreSQL before trusting stored inspections."
        )
    if os.environ.get("ATIS_IMAGE_STORAGE", "db").strip().lower() in {"", "db", "database"}:
        flask_app.logger.warning(
            "Inspection images are stored as database blobs (demo default). This "
            "bloats the database quickly under real volume; set "
            "ATIS_IMAGE_STORAGE=s3 with a bucket for production."
        )
    if flask_app.config["RETENTION_DAYS"] <= 0 and flask_app.config["AUDIT_RETENTION_DAYS"] <= 0:
        flask_app.logger.warning(
            "No data-retention policy is configured (ATIS_RETENTION_DAYS and "
            "ATIS_AUDIT_RETENTION_DAYS are both 0). Inspections store plates and "
            "images and audit events store IP addresses — all personal data. Set "
            "a retention window and schedule `flask atis-purge-expired`."
        )


def register_context_processors(flask_app):
    @flask_app.context_processor
    def inject_nha_status():
        """Expose common NHA header counts and session info to all templates.

        Permissions come from ``g.current_user`` (loaded fresh from the DB by
        the before_request hook), not the session snapshot, so role changes and
        deactivations take effect on the next request. The alert queries are
        memoized on ``g`` so multi-render requests (e.g. error pages) pay for
        them once, and ``joinedload`` populates ``alert.inspection`` up front —
        previously each of the 5 dropdown rows lazy-loaded its inspection.
        """
        user = getattr(g, "current_user", None)
        if user is None:
            return {}
        cached = getattr(g, "_nha_status_cache", None)
        if cached is None:
            cached = {
                "pending_alert_count": Alert.query.filter_by(status="pending").count(),
                "recent_alerts": (
                    Alert.query
                    .options(joinedload(Alert.inspection))
                    .order_by(Alert.created_at.desc())
                    .limit(5)
                    .all()
                ),
            }
            g._nha_status_cache = cached
        return {
            **cached,
            "current_user": user.email,
            "current_role": user.role,
            "can_manage_alerts": user.role in ALERT_MANAGER_ROLES,
            "can_view_reports": user.role in REPORT_VIEWER_ROLES,
            "can_run_inspections": user.role in INSPECTION_OPERATOR_ROLES,
            "can_review_inspections": user.role in INSPECTION_REVIEWER_ROLES,
            "can_manage_users": user.role in ADMIN_ROLES,
        }


PUBLIC_ENDPOINTS = {"login", "mfa_verify", "static", "healthz", "readyz", "metrics"}


def register_health_endpoint(flask_app):
    @flask_app.get("/healthz")
    def healthz():
        """Unauthenticated liveness probe for container/platform health checks.

        Deliberately cheap (no DB, no model): it answers "is the web process
        serving requests", so an outage of a dependency doesn't put the
        container into a restart loop that can't fix it.
        """
        return jsonify({"status": "ok"}), 200

    @flask_app.get("/readyz")
    def readyz():
        """Readiness probe: is this instance able to serve real traffic?

        Unlike /healthz, this checks the dependencies a request actually needs —
        the database (a trivial round-trip) and, when warmup is enabled, that the
        model weights are resolvable. Returns 503 when not ready so a load
        balancer stops routing to an instance whose DB is down or whose
        migrations have not run, instead of serving errors.
        """
        checks = {"database": False, "model": None}
        status_code = 200

        try:
            db.session.execute(sql_text("SELECT 1"))
            checks["database"] = True
        except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
            checks["database"] = False
            checks["database_error"] = str(exc)
            status_code = 503

        if env_bool("ATIS_WARMUP", False):
            model_path = find_model_path()
            checks["model"] = bool(model_path)
            if not model_path:
                status_code = 503

        checks["status"] = "ok" if status_code == 200 else "unavailable"
        return jsonify(checks), status_code


def register_request_hooks(flask_app):
    @flask_app.before_request
    def require_authenticated_session():
        """Global safety net: enforce login on every endpoint except public ones."""
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None
        user = session_user()
        if user is None:
            # Drop any stale auth session, but preserve an in-progress MFA step
            # (password verified, awaiting the second factor) so navigating during
            # the flow doesn't force the password to be re-entered.
            pending_mfa = session.get("mfa_pending_user_id")
            session.clear()
            if pending_mfa is not None:
                session["mfa_pending_user_id"] = pending_mfa
            return auth_failure_response()
        g.current_user = user
        return None


def register_cli(flask_app):
    @flask_app.cli.command("stamp-legacy-schema")
    def stamp_legacy_schema():
        """Stamp an old create_all database so Alembic can upgrade it.

        Early deployments created tables directly before Alembic tracked them.
        Those databases have application tables such as users, but no
        alembic_version row. Detect the newest represented migration so the
        normal chain can continue without replaying columns that already exist.
        """
        inspector = inspect_database(db.engine)
        tables = set(inspector.get_table_names())
        if "users" not in tables:
            click.echo("No legacy users table found; fresh migrations can run normally.")
            return

        column_cache = {}

        def columns_for(table_name):
            if table_name not in tables:
                return set()
            if table_name not in column_cache:
                column_cache[table_name] = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
            return column_cache[table_name]

        def has_tables(*table_names):
            return all(table_name in tables for table_name in table_names)

        def has_columns(table_name, *column_names):
            columns = columns_for(table_name)
            return all(column_name in columns for column_name in column_names)

        # 0005 only creates indexes. A legacy create_all schema can already have
        # later columns without every Alembic-named index, so the stamp target is
        # based on structural tables/columns to avoid duplicate-column failures.
        revision_checks = [
            (
                "0001_initial_postgresql_schema",
                lambda: has_tables("users", "inspections", "alerts"),
            ),
            ("0002_password_hash", lambda: has_columns("users", "password_hash")),
            (
                "0003_add_image_blob_columns",
                lambda: has_columns("inspections", "image_data", "image_mime"),
            ),
            ("0004_add_boxes_column", lambda: has_columns("inspections", "boxes")),
            ("0005_add_query_indexes", lambda: True),
            (
                "0006_add_alert_audit_fields",
                lambda: has_columns(
                    "alerts",
                    "acknowledged_by_id",
                    "acknowledged_at",
                    "resolved_by_id",
                    "resolved_at",
                ),
            ),
            (
                "0007_add_image_storage_metadata",
                lambda: has_columns(
                    "inspections",
                    "image_storage",
                    "image_object_key",
                    "image_size",
                ),
            ),
            (
                "0008_audit_checksum",
                lambda: has_columns("inspections", "created_by_id", "image_checksum"),
            ),
            ("0009_add_user_active_flag", lambda: has_columns("users", "is_active")),
            ("0010_add_audit_events", lambda: has_tables("audit_events")),
            (
                "0011_review_workflow",
                lambda: has_columns(
                    "inspections",
                    "review_status",
                    "review_notes",
                    "reviewer_id",
                    "reviewed_at",
                    "correction_label",
                ),
            ),
            (
                "0012_normalize_defects",
                lambda: has_tables("defect_types", "inspection_defects"),
            ),
            (
                "0013_enrich_alert_workflow",
                lambda: has_tables("alert_comments")
                and has_columns(
                    "alerts",
                    "priority",
                    "severity",
                    "assigned_user_id",
                    "assigned_team",
                    "sla_due_at",
                    "escalation_status",
                    "resolution_category",
                ),
            ),
            (
                "0014_model_metadata",
                lambda: has_columns(
                    "inspections",
                    "predicted_class",
                    "model_path",
                    "model_version",
                    "model_threshold",
                    "low_confidence",
                    "inference_ms",
                ),
            ),
            (
                "0015_locations_cameras",
                lambda: has_tables("locations", "cameras")
                and has_columns("inspections", "location_id", "camera_id"),
            ),
            ("0016_add_saved_filters", lambda: has_tables("saved_filters")),
            (
                "0017_add_anpr_fields",
                lambda: has_columns(
                    "inspections",
                    "plate_source",
                    "plate_confidence",
                    "plate_raw_text",
                ),
            ),
        ]

        revision = None
        revision_positions = {}
        for candidate, schema_matches in revision_checks:
            revision_positions[candidate] = len(revision_positions)
            if not schema_matches():
                break
            revision = candidate

        if revision is None:
            click.echo("Legacy users table found, but required base tables are missing.")
            raise click.ClickException("Cannot determine a safe Alembic stamp revision.")

        current_revision = None
        if "alembic_version" in tables:
            current_revision = db.session.execute(
                sql_text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()

        if current_revision:
            current_position = revision_positions.get(current_revision)
            detected_position = revision_positions[revision]
            if current_position is None:
                click.echo(
                    f"Alembic version table already points at {current_revision}; "
                    "no automatic legacy stamp repair was attempted."
                )
                return
            if current_position >= detected_position:
                click.echo(
                    f"Alembic version table already points at {current_revision}; "
                    "no stamp needed."
                )
                return

        stamp_migration(revision=revision)
        if current_revision:
            click.echo(f"Advanced stale Alembic stamp from {current_revision} to {revision}.")
        else:
            click.echo(f"Stamped legacy database at {revision}.")

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

    @flask_app.cli.command("atis-purge-expired")
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        default=False,
        help="Actually delete. Without this flag the command is a dry run.",
    )
    @click.option("--retention-days", type=int, default=None, help="Override ATIS_RETENTION_DAYS.")
    @click.option("--audit-retention-days", type=int, default=None, help="Override ATIS_AUDIT_RETENTION_DAYS.")
    def atis_purge_expired(apply_changes, retention_days, audit_retention_days):
        """Delete inspections and audit events past their retention window.

        Personal data (plates, images, IP addresses) is aged out here. Runs as a
        dry run by default; pass --apply to commit. Schedule from cron.
        """
        from services.retention import purge_expired

        retention = current_app.config["RETENTION_DAYS"] if retention_days is None else retention_days
        audit_retention = (
            current_app.config["AUDIT_RETENTION_DAYS"]
            if audit_retention_days is None
            else audit_retention_days
        )
        if retention <= 0 and audit_retention <= 0:
            click.echo(
                "No retention window set (ATIS_RETENTION_DAYS / "
                "ATIS_AUDIT_RETENTION_DAYS are 0). Nothing to purge."
            )
            return

        summary = purge_expired(
            retention_days=retention,
            audit_retention_days=audit_retention,
            dry_run=not apply_changes,
        )
        verb = "Deleted" if apply_changes else "Would delete"
        click.echo(
            f"{verb}: {summary['inspections_deleted']} inspection(s), "
            f"{summary['alerts_deleted']} alert(s), "
            f"{summary['audit_events_deleted']} audit event(s)."
        )
        if not apply_changes:
            click.echo("Dry run — re-run with --apply to commit.")

    @flask_app.cli.command("atis-export-plate")
    @click.option("--plate", prompt=True, help="Plate to export all held records for.")
    def atis_export_plate(plate):
        """Print every record held for a plate (data-subject access request)."""
        import json as _json

        from services.retention import export_plate_data

        click.echo(_json.dumps(export_plate_data(plate), indent=2))

    @flask_app.cli.command("atis-erase-plate")
    @click.option("--plate", prompt=True, help="Plate to erase all held records for.")
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        default=False,
        help="Actually delete. Without this flag the command is a dry run.",
    )
    def atis_erase_plate(plate, apply_changes):
        """Erase every inspection/image/alert held for a plate (right to erasure)."""
        from services.retention import erase_plate_data

        summary = erase_plate_data(plate, dry_run=not apply_changes)
        verb = "Erased" if apply_changes else "Would erase"
        click.echo(
            f"{verb} {summary['inspections_deleted']} inspection(s) and "
            f"{summary['alerts_deleted']} alert(s) for plate {summary['plate']}."
        )
        if not apply_changes:
            click.echo("Dry run — re-run with --apply to commit.")

    @flask_app.cli.command("atis-model-monitor")
    @click.option("--window-days", type=int, default=7, show_default=True)
    @click.option(
        "--strict",
        is_flag=True,
        default=False,
        help="Exit non-zero when a safety threshold is breached (for cron alerting).",
    )
    def atis_model_monitor(window_days, strict):
        """Report live model behaviour and drift from stored inspections."""
        import json as _json

        from services.model_monitoring import compute_monitoring_metrics, evaluate_health

        metrics = compute_monitoring_metrics(window_days=window_days)
        health = evaluate_health(metrics)
        click.echo(_json.dumps({"metrics": metrics, "health": health}, indent=2))
        if strict and not health["ok"]:
            raise click.ClickException("; ".join(health["breaches"]))

    @flask_app.cli.command("atis-verify-audit")
    def atis_verify_audit():
        """Verify the audit-log hash chain and report the first tampered row."""
        import json as _json

        from services.audit import verify_audit_chain

        report = verify_audit_chain()
        click.echo(_json.dumps(report, indent=2))
        if not report["ok"]:
            raise click.ClickException(
                f"Audit chain broken at event #{report['first_broken_id']}: {report['reason']}"
            )


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


app = create_app()


if __name__ == "__main__":
    warmup_model(fail_hard=False, flask_app=app)
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
