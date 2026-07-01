"""
NHA - Automated Highway Inspection System
Main Application File (Flask)

This file handles all the web routes, database connections, and logic for the application.
It connects the operator dashboard to the trained ATIS tire classifier.
"""

import os
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import click
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError

from atis_inference import classify_tyre_image, find_model_path, load_classifier
from config import Config
from models import Alert, Inspection, User, db

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

# Initialize the Flask application
app = Flask(__name__)

# Centralised, environment-driven configuration (see config.py).
# validate() fails fast in production if the secret key is missing/insecure.
app.config.from_object(Config)
Config.validate()

# Upload configuration
UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}

# Live camera configuration
LIVE_DEFAULT_ZONES = BASE_DIR / "config" / "live_zones.json"

# Initialize the database with the app
db.init_app(app)
migrate = Migrate(app, db)

# CSRF protection for all state-changing form posts.
csrf = CSRFProtect(app)

# Rate limiting (brute-force protection on auth). In-memory by default; point
# RATELIMIT_STORAGE_URI at Redis for multi-worker production deployments.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=app.config["RATELIMIT_STORAGE_URI"],
)


# -------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------

@app.context_processor
def inject_nha_status():
    """Expose common NHA header counts and session info to all templates."""
    if "user" not in session:
        return {}
    return {
        "pending_alert_count": Alert.query.filter_by(status="pending").count(),
        "current_user": session.get("user", ""),
        "current_role": session.get("role", ""),
        "recent_alerts": (
            Alert.query
            .join(Inspection)
            .order_by(Alert.created_at.desc())
            .limit(5)
            .all()
        ),
    }


def allowed_file(filename):
    """Check if a filename has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def wants_json_response():
    """Return True when the client expects a JSON API response."""
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )


# -------------------------------------------------------------------------
# AUTHENTICATION / AUTHORIZATION
# -------------------------------------------------------------------------

# Endpoints reachable without an authenticated session.
PUBLIC_ENDPOINTS = {"login", "static"}


def _auth_failure_response():
    """Return a 401 JSON for API/XHR callers, otherwise redirect to login."""
    if request.path.startswith("/api/") or wants_json_response():
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for("login"))


@app.before_request
def require_authenticated_session():
    """Global safety net: enforce login on every endpoint except the public ones."""
    endpoint = request.endpoint
    if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
        return None
    if "user" not in session:
        return _auth_failure_response()
    return None


def login_required(view):
    """Decorator enforcing an authenticated session for a single view."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return _auth_failure_response()
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Decorator restricting a view to the given roles (e.g. "Admin", "Supervisor").

    Ready for sensitive routes (user management, alert resolution) as they are added.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                return _auth_failure_response()
            if session.get("role") not in roles:
                if request.path.startswith("/api/") or wants_json_response():
                    return jsonify({"error": "Forbidden"}), 403
                return render_template("403.html"), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def env_float(name, default):
    """Read a float environment variable with a safe fallback."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_int(name, default):
    """Read an integer environment variable with a safe fallback."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def live_zones_path():
    """Return the configured live-zone JSON path."""
    raw_path = os.environ.get("ATIS_LIVE_ZONES", str(LIVE_DEFAULT_ZONES))
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def live_camera_source():
    """Return the OpenCV camera source, supporting indexes, files, and streams."""
    raw_source = os.environ.get("ATIS_LIVE_CAMERA", "0").strip() or "0"
    try:
        return int(raw_source)
    except ValueError:
        path = Path(raw_source)
        if not path.is_absolute() and (BASE_DIR / path).exists():
            return str(BASE_DIR / path)
        return raw_source


def live_stream_args():
    """Build an args-like object compatible with the OpenCV live pipeline."""
    return SimpleNamespace(
        analyze_interval=env_float("ATIS_LIVE_ANALYZE_INTERVAL", 0.5),
        motion_threshold=env_float("ATIS_LIVE_MOTION_THRESHOLD", 8.0),
        unsafe_streak=env_int("ATIS_LIVE_UNSAFE_STREAK", 3),
        cooldown=env_float("ATIS_LIVE_COOLDOWN", 20.0),
        location=os.environ.get("ATIS_LIVE_LOCATION", "Dashboard Live Feed"),
        camera_label=os.environ.get("ATIS_LIVE_CAMERA_LABEL", "DASHBOARD-LIVE"),
    )


def display_path(path):
    """Show paths relative to the project when possible."""
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def encode_mjpeg_frame(frame):
    """Encode an OpenCV frame for multipart MJPEG streaming."""
    import cv2

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        return None
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"


def live_message_frame(title, lines=None):
    """Create a readable placeholder frame for camera/config errors."""
    import cv2
    import numpy as np

    lines = lines or []
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (28, 41, 34)
    cv2.rectangle(frame, (0, 0), (1280, 72), (16, 41, 31), -1)
    cv2.putText(frame, "ATIS LIVE", (32, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (66, 197, 244), 3)
    cv2.putText(frame, title, (60, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (255, 255, 255), 3)

    y = 286
    for raw_line in lines:
        for line in str(raw_line).splitlines() or [""]:
            for start in range(0, len(line), 72):
                cv2.putText(
                    frame,
                    line[start:start + 72],
                    (60, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.72,
                    (210, 224, 216),
                    2,
                )
                y += 38
            if not line:
                y += 38
        if y > 650:
            break
    return frame


def live_message_stream(title, lines=None):
    """Yield an MJPEG error/status frame repeatedly."""
    while True:
        payload = encode_mjpeg_frame(live_message_frame(title, lines))
        if payload:
            yield payload
        time.sleep(1.0)


def generate_live_frames():
    """Generate annotated live inspection frames for the dashboard."""
    try:
        import cv2
        from live_video_inspection import (
            InspectionLogger,
            RuntimeState,
            crop_zone,
            draw_header,
            draw_zone_overlay,
            load_zones,
            maybe_analyze_zone,
        )
    except Exception as exc:
        yield from live_message_stream(
            "Live video dependency unavailable",
            ["Install requirements and verify OpenCV/Ultralytics imports.", str(exc)],
        )
        return

    zones_path = live_zones_path()
    try:
        zones = load_zones(zones_path)
    except SystemExit as exc:
        yield from live_message_stream(
            "Zone calibration required",
            [str(exc), "Run: python3 calibrate_live_zones.py --camera 0"],
        )
        return
    except Exception as exc:
        yield from live_message_stream("Could not load live zones", [str(exc)])
        return

    args = live_stream_args()
    runtime = RuntimeState(zones)
    logger = InspectionLogger(
        enabled=env_bool("ATIS_LIVE_DB_LOG", True),
        flask_app=app,
        db_obj=db,
        inspection_model=Inspection,
        alert_model=Alert,
        upload_folder=UPLOAD_FOLDER,
    )

    source = live_camera_source()
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        yield from live_message_stream(
            "Camera feed unavailable",
            [
                f"OpenCV could not open source: {source}",
                "Check ATIS_LIVE_CAMERA or connect camera index 0.",
            ],
        )
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, env_int("ATIS_LIVE_WIDTH", 1280))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, env_int("ATIS_LIVE_HEIGHT", 720))

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if isinstance(source, str) and Path(source).exists():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                payload = encode_mjpeg_frame(live_message_frame("Camera frame read failed"))
                if payload:
                    yield payload
                time.sleep(0.5)
                continue

            display = frame.copy()
            now = time.monotonic()
            for zone in zones:
                crop, rect = crop_zone(frame, zone)
                maybe_analyze_zone(
                    crop,
                    rect,
                    runtime.zone_states[zone.name],
                    args,
                    logger,
                    frame.copy(),
                    zone,
                    now,
                )
                draw_zone_overlay(display, zone, rect, runtime.zone_states[zone.name], args.motion_threshold)

            draw_header(display, args, runtime, controls_text="dashboard stream")
            payload = encode_mjpeg_frame(display)
            if payload:
                yield payload
    finally:
        cap.release()


DEMO_USERS = [
    ("admin@atis.com", "admin123", "Admin"),
    ("operator@atis.com", "operator123", "Operator"),
    ("supervisor@atis.com", "super123", "Supervisor"),
    ("inspector@atis.com", "inspect123", "Inspector"),
]


def ensure_local_database():
    """Create the local SQLite tables and, in development only, seed demo users.

    Demo accounts are NEVER created in production: seeding is gated on both the
    SQLite backend and Config.SEED_DEMO_DATA (false when ATIS_ENV=production).
    Passwords are stored hashed via User.set_password().
    """
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    with app.app_context():
        db.create_all()

        if not app.config["SEED_DEMO_DATA"]:
            return
        if User.query.count() > 0:
            return

        for email, password, role in DEMO_USERS:
            user = User(email=email, role=role)
            user.set_password(password)
            db.session.add(user)
        db.session.commit()


ensure_local_database()


def warmup_model(fail_hard: bool = False) -> bool:
    """Load the classifier and run one dummy inference at boot.

    Ensures the first real request isn't slow and that a missing/corrupt model is
    detected early. In production (fail_hard=True) a failure aborts startup; in dev
    it only logs a warning so non-inference pages still work.
    """
    try:
        import numpy as np

        model = load_classifier()
        model.predict(np.zeros((224, 224, 3), dtype=np.uint8), verbose=False)
        app.logger.info("ATIS model warmup complete: %s", find_model_path())
        return True
    except Exception as exc:  # noqa: BLE001 - surface any load/inference failure
        message = f"ATIS model warmup failed: {exc}"
        if fail_hard:
            raise RuntimeError(message) from exc
        app.logger.warning(message)
        return False


# Opt-in warmup for the web server (set ATIS_WARMUP=1 when running gunicorn).
# Fails hard in production so a broken model never serves traffic silently.
if env_bool("ATIS_WARMUP", False):
    warmup_model(fail_hard=app.config["IS_PRODUCTION"])


# -------------------------------------------------------------------------
# CLI COMMANDS
# -------------------------------------------------------------------------

@app.cli.command("create-admin")
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
    """Create or update a user with a securely hashed password.

    The supported way to provision the first administrator in production
    (where demo seeding is disabled). Usage:

        ATIS_ENV=production flask --app app create-admin
    """
    db.create_all()
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


# -------------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------------

@app.route("/")
def index():
    """
    The root route.
    If the user is logged in, send them to the dashboard.
    If not, send them to the login page.
    """
    if "user" in session:
        return redirect(url_for("dashboard"))
    
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    """
    Login Route.
    GET: Renders the login form.
    POST: Processes the login form data.
    """
    if request.method == "POST":
        # Get data from the form
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        login_email = email

        # Demo convenience aliases (nha.gov.pk -> atis.com) are disabled in
        # production; see Config.ENABLE_DEMO_LOGIN_ALIASES.
        if app.config["ENABLE_DEMO_LOGIN_ALIASES"]:
            demo_aliases = {
                "admin@nha.gov.pk": "admin@atis.com",
                "operator@nha.gov.pk": "operator@atis.com",
                "supervisor@nha.gov.pk": "supervisor@atis.com",
                "inspector@nha.gov.pk": "inspector@atis.com",
            }
            login_email = demo_aliases.get(email, email)

        # Check if user exists in the database
        user = User.query.filter_by(email=login_email).first()

        # Verify the password against the stored salted hash.
        if user and user.check_password(password):
            # Login successful: store user in session
            session["user"] = user.email
            session["role"] = user.role
            return redirect(url_for("dashboard"))
        else:
            # Login failed
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    """
    Dashboard Route.
    Shows the main overview: inspection stats, recent inspections, and alerts.
    """
    # Security check: must be logged in
    if "user" not in session:
        return redirect(url_for("login"))

    # Fetch the 10 most recent inspections for the table
    inspections = Inspection.query.order_by(Inspection.timestamp.desc()).limit(10).all()

    # Calculate statistics for the top cards
    total = Inspection.query.count()
    safe = Inspection.query.filter_by(status="safe").count()
    unsafe = Inspection.query.filter_by(status="unsafe").count()
    pending_alerts = Alert.query.filter_by(status="pending").count()
    
    # Avoid division by zero threshold
    pass_rate = 0
    if total > 0:
        pass_rate = round((safe / total * 100), 1)

    # Package stats into a dictionary
    stats = {
        "total": total,
        "safe": safe,
        "unsafe": unsafe,
        "pending_alerts": pending_alerts,
        "pass_rate": pass_rate,
    }

    # Fetch recent alerts for the notification dropdown (limit 5)
    recent_alerts = (
        Alert.query
        .join(Inspection)
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "index.html",
        user=session["user"],
        role=session["role"],
        inspections=inspections,
        stats=stats,
        recent_alerts=recent_alerts,
    )


@app.route("/alerts")
def alerts():
    """
    Alerts Page.
    Displays all alerts and allows filtering by status (Pending, Resolved, etc).
    """
    if "user" not in session:
        return redirect(url_for("login"))

    # Get all alerts, joined with inspection data to show plate numbers, etc.
    alert_rows = (
        Alert.query
        .join(Inspection)
        .order_by(Alert.created_at.desc())
        .all()
    )
    
    # Count how many are pending (for the badge)
    pending_count = Alert.query.filter_by(status="pending").count()

    return render_template(
        "alerts.html",
        user=session["user"],
        role=session["role"],
        alerts=alert_rows,
        pending_count=pending_count,
    )


@app.route("/history")
def history():
    """
    History Page.
    Shows a complete log of all inspections stored in the system.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    # Fetch all inspections, newest first
    inspections = Inspection.query.order_by(Inspection.timestamp.desc()).all()
    total_count = len(inspections)

    return render_template(
        "history.html",
        user=session["user"],
        role=session["role"],
        inspections=inspections,
        total_count=total_count,
    )


@app.route("/reports")
def reports():
    """
    Reports Page.
    Generate charts from real data and export PDF reports.
    """
    if "user" not in session:
        return redirect(url_for("login"))
        
    return render_template("reports.html", user=session["user"], role=session["role"])


@app.route("/inspection/<int:inspection_id>")
def inspection_detail(inspection_id):
    """
    Inspection Detail Page.
    Shows full details for a specific inspection ID.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    # Get the inspection or show 404 if not found
    insp = Inspection.query.get_or_404(inspection_id)
    
    # Also get any alerts related to this inspection
    related_alerts = Alert.query.filter_by(inspection_id=insp.id).order_by(Alert.created_at.desc()).all()

    return render_template(
        "inspection.html",
        user=session["user"],
        role=session["role"],
        inspection=insp,
        alerts=related_alerts,
    )


@app.route("/inspect")
def new_inspection():
    """
    New Inspection Page.
    Shows a form for uploading an inspection image and submitting for AI analysis.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "new_inspection.html",
        user=session["user"],
        role=session["role"],
    )


@app.route("/live")
def live_feed():
    """
    Live Camera Page.
    Shows the Python/OpenCV tire inspection stream inside the dashboard.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    args = live_stream_args()
    zones_path = live_zones_path()
    return render_template(
        "live_feed.html",
        user=session["user"],
        role=session["role"],
        camera_source=os.environ.get("ATIS_LIVE_CAMERA", "0"),
        zones_path=display_path(zones_path),
        zones_configured=zones_path.exists(),
        db_logging=env_bool("ATIS_LIVE_DB_LOG", True),
        analyze_interval=args.analyze_interval,
        motion_threshold=args.motion_threshold,
        unsafe_streak=args.unsafe_streak,
        cooldown=int(args.cooldown),
    )


@app.route("/live/stream")
def live_stream():
    """
    MJPEG stream endpoint for the live dashboard camera area.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    return Response(
        generate_live_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/logout")
def logout():
    """
    Logs the user out by clearing the session.
    """
    session.clear()
    return redirect(url_for("login"))


# -------------------------------------------------------------------------
# PREDICTION ENDPOINT
# -------------------------------------------------------------------------

@app.route("/predict", methods=["POST"])
def predict():
    """
    Prediction API Endpoint.
    Accepts a multipart form with an image file + optional metadata.
    Runs the trained ATIS YOLO classifier, saves an Inspection record, and redirects to detail page.
    """
    if "user" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    # --- 1. Validate the uploaded file ---
    if "image" not in request.files:
        flash("No image file uploaded.", "error")
        return redirect(url_for("new_inspection"))

    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        flash("Invalid file. Please upload a JPG, PNG, BMP, or WebP image.", "error")
        return redirect(url_for("new_inspection"))

    # --- 2. Save the uploaded image ---
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(save_path)

    # Verify the saved file is a genuine image, not just a permitted extension.
    # (Extension checks alone are spoofable; this rejects disguised/corrupt files.)
    try:
        with Image.open(save_path) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError):
        os.remove(save_path)
        flash("Uploaded file is not a valid image.", "error")
        return redirect(url_for("new_inspection"))

    # Relative path for storing in DB and serving via static files
    image_rel_path = f"uploads/{unique_name}"

    # --- 3. Get form metadata ---
    plate = request.form.get("plate", "").strip() or None
    location = request.form.get("location", "").strip() or "Unknown Location"
    camera = request.form.get("camera", "").strip() or None

    # --- 4. Run trained ATIS classification inference ---
    bounding_boxes = []
    try:
        prediction = classify_tyre_image(save_path)
    except Exception as exc:
        print(f"ATIS classifier inference error: {exc}")
        flash("AI model inference failed. Please verify dependencies and model weights.", "error")
        return redirect(url_for("new_inspection"))

    status = prediction["status"]
    confidence = prediction["confidence"]
    defects_list = prediction["defects"]
    predicted_class = prediction["predicted_class"]
    model_path = prediction["model_path"]

    # --- 5. Save Inspection to database ---
    defects_str = ",".join(defects_list) if defects_list else None

    inspection = Inspection(
        timestamp=datetime.utcnow(),
        plate=plate,
        location=location,
        camera=camera,
        status=status,
        confidence=confidence,
        defects=defects_str,
        image_path=image_rel_path,
    )
    db.session.add(inspection)
    db.session.flush()  # Get the ID

    # --- 6. Auto-create Alert if unsafe ---
    if status == "unsafe":
        alert = Alert(
            inspection_id=inspection.id,
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.session.add(alert)

    db.session.commit()

    if wants_json_response():
        return jsonify({
            "inspection_id": inspection.id,
            "status": status,
            "confidence": confidence,
            "defects": defects_list,
            "bounding_boxes": bounding_boxes,
            "predicted_class": predicted_class,
            "model_path": model_path,
            "image_url": url_for("static", filename=image_rel_path),
            "detail_url": url_for("inspection_detail", inspection_id=inspection.id),
        })

    flash(
        f"Inspection #{inspection.id} completed — {predicted_class.upper()} ({confidence}%)",
        "success" if status == "safe" else "warning",
    )
    return redirect(url_for("inspection_detail", inspection_id=inspection.id))


# -------------------------------------------------------------------------
# REPORTS API ENDPOINTS
# -------------------------------------------------------------------------

@app.route("/api/reports/safety-trend")
def api_safety_trend():
    """
    Returns daily safe vs unsafe counts for charting.
    Query params: from (YYYY-MM-DD), to (YYYY-MM-DD)
    """
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)  # inclusive
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Query inspections in range
    inspections = Inspection.query.filter(
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
    ).all()

    # Group by date
    daily_safe = Counter()
    daily_unsafe = Counter()
    for insp in inspections:
        day = insp.timestamp.strftime("%Y-%m-%d")
        if insp.status == "safe":
            daily_safe[day] += 1
        else:
            daily_unsafe[day] += 1

    # Build continuous date labels
    labels = []
    safe_counts = []
    unsafe_counts = []
    current = start
    while current < end:
        day_str = current.strftime("%Y-%m-%d")
        label = current.strftime("%b %d")
        labels.append(label)
        safe_counts.append(daily_safe.get(day_str, 0))
        unsafe_counts.append(daily_unsafe.get(day_str, 0))
        current += timedelta(days=1)

    return jsonify({"labels": labels, "safe": safe_counts, "unsafe": unsafe_counts})


@app.route("/api/reports/defect-distribution")
def api_defect_distribution():
    """
    Returns counts of each defect type for charting.
    Query params: from (YYYY-MM-DD), to (YYYY-MM-DD)
    """
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    inspections = Inspection.query.filter(
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
    ).all()

    defect_counts = Counter()
    for insp in inspections:
        for d in insp.defect_list:
            defect_counts[d] += 1

    # Sort by count descending
    sorted_defects = sorted(defect_counts.items(), key=lambda x: x[1], reverse=True)
    labels = [d[0] for d in sorted_defects]
    values = [d[1] for d in sorted_defects]

    return jsonify({"labels": labels, "values": values})


@app.route("/api/reports/daily-summary")
def api_daily_summary():
    """
    Returns daily total and unsafe counts for charting.
    Query params: from (YYYY-MM-DD), to (YYYY-MM-DD)
    """
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    inspections = Inspection.query.filter(
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
    ).all()

    daily_total = Counter()
    daily_unsafe = Counter()
    for insp in inspections:
        day = insp.timestamp.strftime("%Y-%m-%d")
        daily_total[day] += 1
        if insp.status == "unsafe":
            daily_unsafe[day] += 1

    labels = []
    total_counts = []
    unsafe_counts = []
    current = start
    while current < end:
        day_str = current.strftime("%Y-%m-%d")
        label = current.strftime("%b %d")
        labels.append(label)
        total_counts.append(daily_total.get(day_str, 0))
        unsafe_counts.append(daily_unsafe.get(day_str, 0))
        current += timedelta(days=1)

    return jsonify({"labels": labels, "total": total_counts, "unsafe": unsafe_counts})


# -------------------------------------------------------------------------
# PDF EXPORT
# -------------------------------------------------------------------------

@app.route("/api/reports/export-pdf")
def export_pdf():
    """
    Generates a PDF report of inspections within a date range.
    Returns the PDF as a downloadable file.
    """
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    inspections = Inspection.query.filter(
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
    ).order_by(Inspection.timestamp.desc()).all()

    # --- Build PDF with reportlab ---
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=6,
        textColor=colors.HexColor("#006400"),
    )
    elements.append(Paragraph("NHA — Inspection Report", title_style))

    # Date range subtitle
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        spaceAfter=16,
    )
    elements.append(
        Paragraph(
            f"Period: {start.strftime('%B %d, %Y')} — {(end - timedelta(days=1)).strftime('%B %d, %Y')}  |  "
            f"Total: {len(inspections)} inspections  |  Generated: {datetime.utcnow().strftime('%B %d, %Y %I:%M %p')}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 8))

    if inspections:
        # Table header
        table_data = [["ID", "Date & Time", "Plate", "Location", "Camera", "Status", "Confidence", "Defects"]]

        # Table rows
        cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10)
        for insp in inspections:
            table_data.append([
                str(insp.id),
                insp.timestamp.strftime("%b %d, %Y %I:%M %p"),
                insp.plate or "—",
                Paragraph(insp.location[:35], cell_style),
                insp.camera or "—",
                insp.status.upper(),
                f"{insp.confidence}%",
                Paragraph(insp.defects or "None", cell_style),
            ])

        # Column widths
        col_widths = [0.4 * inch, 1.3 * inch, 0.8 * inch, 2.2 * inch, 0.7 * inch, 0.6 * inch, 0.8 * inch, 2.0 * inch]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header style
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#006400")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Body style
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            # Alternating row colors
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f7f0")]),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),    # ID centered
            ("ALIGN", (5, 0), (6, -1), "CENTER"),     # Status + confidence centered
        ]))

        # Color-code status cells
        for i, insp in enumerate(inspections, start=1):
            if insp.status == "unsafe":
                table.setStyle(TableStyle([
                    ("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#dc2626")),
                    ("FONTNAME", (5, i), (5, i), "Helvetica-Bold"),
                ]))
            else:
                table.setStyle(TableStyle([
                    ("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#16a34a")),
                ]))

        elements.append(table)
    else:
        elements.append(Paragraph("No inspections found in the selected date range.", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    filename = f"NHA_Report_{date_from}_to_{date_to}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


# -------------------------------------------------------------------------
# ERROR HANDLERS
# -------------------------------------------------------------------------

@app.errorhandler(413)
def request_entity_too_large(e):
    """Reject uploads that exceed MAX_CONTENT_LENGTH with a clean message."""
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    message = f"File too large. Maximum upload size is {limit_mb} MB."
    if request.path.startswith("/api/") or wants_json_response():
        return jsonify({"error": message}), 413
    flash(message, "error")
    return redirect(url_for("new_inspection"))


@app.errorhandler(404)
def page_not_found(e):
    """Show a custom 404 page when a URL is not found."""
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    """Show a custom 500 page for internal server errors."""
    return render_template("500.html"), 500


# Main entry point
#
# NOTE: this development server (and the debug flag) is for local use only.
# In production run a WSGI server, e.g. `gunicorn app:app`, with ATIS_ENV=production.
if __name__ == "__main__":
    # Best-effort warmup for the dev server (logs a warning if weights are missing).
    warmup_model(fail_hard=False)
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
