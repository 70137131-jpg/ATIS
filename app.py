"""
NHA - Automated Highway Inspection System
Main Application File (Flask)

This file handles all the web routes, database connections, and logic for the application.
It connects the operator dashboard to the trained ATIS tire classifier.
"""

import os
import uuid
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from atis_inference import classify_tyre_image
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


def get_database_url():
    """Return the configured database URL, defaulting to local SQLite."""
    default_sqlite = BASE_DIR / "instance" / "atis.db"
    default_sqlite.parent.mkdir(exist_ok=True)
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{default_sqlite}")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url

# Initialize the Flask application
app = Flask(__name__)

# Secret key for session management (keep this safe in production!)
app.secret_key = os.environ.get("SECRET_KEY", "atis-secret-key-change-in-production")

# Database configuration
database_url = get_database_url()
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if not database_url.startswith("sqlite"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

# Upload configuration
UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}

# Initialize the database with the app
db.init_app(app)
migrate = Migrate(app, db)


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


def ensure_local_database():
    """Create minimal local SQLite tables/users if the demo database is absent."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    with app.app_context():
        db.create_all()
        if User.query.count() > 0:
            return

        db.session.add_all([
            User(email="admin@atis.com", password="admin123", role="Admin"),
            User(email="operator@atis.com", password="operator123", role="Operator"),
            User(email="supervisor@atis.com", password="super123", role="Supervisor"),
            User(email="inspector@atis.com", password="inspect123", role="Inspector"),
        ])
        db.session.commit()


ensure_local_database()


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

        demo_aliases = {
            "admin@nha.gov.pk": "admin@atis.com",
            "operator@nha.gov.pk": "operator@atis.com",
            "supervisor@nha.gov.pk": "supervisor@atis.com",
            "inspector@nha.gov.pk": "inspector@atis.com",
        }
        login_email = demo_aliases.get(email, email)

        # Check if user exists in the database
        user = User.query.filter_by(email=login_email).first()

        # Check password (in a real app, use hashing like bcrypt!)
        if user and user.password == password:
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

@app.errorhandler(404)
def page_not_found(e):
    """Show a custom 404 page when a URL is not found."""
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    """Show a custom 500 page for internal server errors."""
    return render_template("500.html"), 500


# Main entry point
if __name__ == "__main__":
    app.run(debug=True, port=5000)
