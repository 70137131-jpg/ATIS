"""Inspection history, detail, media, and upload routes."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from flask import (
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from PIL import Image, UnidentifiedImageError

from atis_inference import classify_tyre_image
from models import Alert, Camera, DefectType, Inspection, InspectionDefect, Location, SavedFilter, User, db
from routes.common import (
    INSPECTION_REVIEWER_ROLES,
    INSPECTION_OPERATOR_ROLES,
    clean_metadata_value,
    form_error,
    normalize_plate,
    pagination_args,
    roles_required,
    wants_json_response,
)
from services.audit import log_audit_event
from services.anpr import anpr_min_confidence, is_low_confidence, read_plate_image
from services.defects import normalized_defect_name, sync_inspection_defects
from services.image_storage import load_image, signed_image_url, store_image
from services.operations import (
    normalize_operational_name,
    resolve_operational_context,
)


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}
VALID_REVIEW_STATUSES = {
    "pending_review",
    "approved",
    "rejected",
    "false_positive",
    "false_negative",
}
REVIEW_STATUS_LABELS = {
    "pending_review": "Pending Review",
    "approved": "Approved",
    "rejected": "Rejected",
    "false_positive": "False Positive",
    "false_negative": "False Negative",
}
CORRECTION_LABELS = (
    "normal",
    "cracked",
    "not_tyre",
    "low_confidence_normal",
    "other",
)
MAX_REVIEW_NOTES_LENGTH = 2000

def allowed_file(filename):
    """Check if a filename has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _validate_saved_image(save_path):
    try:
        with Image.open(save_path) as probe:
            if probe.width * probe.height > current_app.config["MAX_IMAGE_PIXELS"]:
                return "Uploaded image dimensions are too large."
            probe.verify()
    except (UnidentifiedImageError, OSError):
        return "Uploaded file is not a valid image."
    return None


def _model_fingerprint(model_path):
    if not model_path or not os.path.exists(model_path):
        return None
    digest = sha256()
    try:
        with open(model_path, "rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()[:16]


def _history_filters():
    return {
        "plate": (request.args.get("plate") or "").strip(),
        "status": (request.args.get("status") or "").strip().lower(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
        "defect": (request.args.get("defect") or "").strip(),
        "camera": (request.args.get("camera") or "").strip(),
        "location": (request.args.get("location") or "").strip(),
        "created_by": (request.args.get("created_by") or "").strip(),
        "duplicates": (request.args.get("duplicates") or "").strip(),
    }


def _parse_history_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        flash("Invalid history date filter. Use YYYY-MM-DD.", "error")
        return None


def _pagination_params():
    params = request.args.to_dict(flat=True)
    params.pop("page", None)
    params.pop("per_page", None)
    return params


def _non_empty_history_params():
    filters = _history_filters()
    return {key: value for key, value in filters.items() if value}


def _anpr_issue_condition():
    threshold = anpr_min_confidence()
    return db.or_(
        Inspection.plate.is_(None),
        Inspection.plate == "",
        Inspection.plate_source.in_(("ocr_failed", "tesseract_low_confidence")),
        db.and_(
            Inspection.plate_source.is_not(None),
            Inspection.plate_source != "manual",
            Inspection.plate_confidence.is_not(None),
            Inspection.plate_confidence < threshold,
        ),
    )


def _history_query(filters):
    inspection_query = db.select(Inspection).order_by(Inspection.timestamp.desc())

    if filters["plate"]:
        inspection_query = inspection_query.where(Inspection.plate.ilike(f"%{filters['plate']}%"))
    if filters["status"] in {"safe", "unsafe"}:
        inspection_query = inspection_query.where(Inspection.status == filters["status"])

    date_from = _parse_history_date(filters["date_from"])
    date_to = _parse_history_date(filters["date_to"])
    if date_from:
        inspection_query = inspection_query.where(Inspection.timestamp >= date_from)
    if date_to:
        inspection_query = inspection_query.where(Inspection.timestamp < date_to + timedelta(days=1))

    if filters["defect"]:
        normalized_defect = normalized_defect_name(filters["defect"])
        normalized_subquery = (
            db.select(InspectionDefect.inspection_id)
            .join(DefectType)
            .where(DefectType.normalized_name == normalized_defect)
        )
        inspection_query = inspection_query.where(
            db.or_(
                Inspection.id.in_(normalized_subquery),
                Inspection.defects.ilike(f"%{filters['defect']}%"),
            )
        )

    if filters["camera"]:
        normalized_camera = normalize_operational_name(filters["camera"])
        inspection_query = inspection_query.where(
            db.or_(
                Inspection.camera.ilike(f"%{filters['camera']}%"),
                Inspection.camera_ref.has(Camera.normalized_name.ilike(f"%{normalized_camera}%")),
            )
        )
    if filters["location"]:
        normalized_location = normalize_operational_name(filters["location"])
        inspection_query = inspection_query.where(
            db.or_(
                Inspection.location.ilike(f"%{filters['location']}%"),
                Inspection.location_ref.has(Location.normalized_name.ilike(f"%{normalized_location}%")),
            )
        )
    if filters["created_by"]:
        created_by = filters["created_by"]
        if created_by.isdigit():
            inspection_query = inspection_query.where(Inspection.created_by_id == int(created_by))
        else:
            inspection_query = inspection_query.where(
                Inspection.created_by.has(User.email.ilike(f"%{created_by}%"))
            )
    if filters["duplicates"] == "only":
        duplicate_checksums = (
            db.select(Inspection.image_checksum)
            .where(Inspection.image_checksum.is_not(None), Inspection.image_checksum != "")
            .group_by(Inspection.image_checksum)
            .having(db.func.count(Inspection.id) > 1)
        )
        inspection_query = inspection_query.where(Inspection.image_checksum.in_(duplicate_checksums))

    return inspection_query


def history():
    """Show a complete log of all inspections stored in the system."""
    page, per_page = pagination_args()
    filters = _history_filters()
    inspection_query = _history_query(filters)
    pagination = db.paginate(inspection_query, page=page, per_page=per_page, error_out=False)
    inspections = pagination.items
    total_count = pagination.total
    defect_options = DefectType.query.order_by(DefectType.name.asc()).all()
    created_by_options = User.query.order_by(User.email.asc()).all()
    saved_filters = SavedFilter.query.filter_by(
        user_id=g.current_user.id,
        page="history",
    ).order_by(SavedFilter.name.asc()).all()

    return render_template(
        "history.html",
        user=session["user"],
        role=session["role"],
        inspections=inspections,
        total_count=total_count,
        pagination=pagination,
        filters=filters,
        pagination_params=_pagination_params(),
        defect_options=defect_options,
        created_by_options=created_by_options,
        saved_filters=saved_filters,
        current_filter_params=_non_empty_history_params(),
    )


@roles_required(*INSPECTION_REVIEWER_ROLES)
def anpr_review_queue():
    """List pending inspections whose plate OCR needs human attention."""
    page, per_page = pagination_args(default_per_page=25)
    query = (
        db.select(Inspection)
        .where(
            Inspection.review_status == "pending_review",
            _anpr_issue_condition(),
        )
        .order_by(Inspection.timestamp.desc(), Inspection.id.desc())
    )
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    return render_template(
        "anpr_review_queue.html",
        user=session["user"],
        role=session["role"],
        inspections=pagination.items,
        pagination=pagination,
        min_confidence=anpr_min_confidence(),
    )


def inspection_detail(inspection_id):
    """Show full details for a specific inspection ID."""
    insp = db.get_or_404(Inspection, inspection_id)
    related_alerts = (
        Alert.query
        .filter_by(inspection_id=insp.id)
        .order_by(Alert.created_at.desc())
        .all()
    )
    duplicate_inspections = []
    if insp.image_checksum:
        duplicate_inspections = (
            Inspection.query
            .filter(
                Inspection.image_checksum == insp.image_checksum,
                Inspection.id != insp.id,
            )
            .order_by(Inspection.timestamp.desc())
            .limit(10)
            .all()
        )

    return render_template(
        "inspection.html",
        user=session["user"],
        role=session["role"],
        inspection=insp,
        alerts=related_alerts,
        review_status_labels=REVIEW_STATUS_LABELS,
        correction_labels=CORRECTION_LABELS,
        duplicate_inspections=duplicate_inspections,
    )


def duplicate_compare(inspection_id, other_id):
    """Show two inspections with the same image checksum side by side."""
    left = db.get_or_404(Inspection, inspection_id)
    right = db.get_or_404(Inspection, other_id)
    if not left.image_checksum or left.image_checksum != right.image_checksum:
        return Response("Inspections are not duplicate uploads", status=404)
    return render_template(
        "duplicate_compare.html",
        user=session["user"],
        role=session["role"],
        left=left,
        right=right,
    )


def inspection_image(inspection_id):
    """Serve an inspection's tire image behind login."""
    insp = db.get_or_404(Inspection, inspection_id)
    direct_url = signed_image_url(insp)
    if direct_url:
        return redirect(direct_url)
    image_bytes, image_mime = load_image(insp)
    if image_bytes:
        return Response(image_bytes, mimetype=image_mime or "image/jpeg")
    if insp.image_path:
        disk_path = os.path.join(current_app.static_folder, insp.image_path)
        if os.path.exists(disk_path):
            return send_file(disk_path)
    return Response("Image not found", status=404)


@roles_required(*INSPECTION_OPERATOR_ROLES)
def new_inspection():
    """Render the image-upload inspection form."""
    return render_template(
        "new_inspection.html",
        user=session["user"],
        role=session["role"],
    )


@roles_required(*INSPECTION_OPERATOR_ROLES)
def anpr_preview():
    """Return a best-effort license plate read for an uploaded image."""
    if "image" not in request.files:
        return jsonify({"error": "No image file uploaded."}), 400

    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file. Please upload a JPG, PNG, BMP, or WebP image."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"anpr-{uuid.uuid4().hex}.{ext}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    save_path = os.path.join(upload_folder, unique_name)
    os.makedirs(upload_folder, exist_ok=True)
    file.save(save_path)

    try:
        validation_error = _validate_saved_image(save_path)
        if validation_error:
            return jsonify({"error": validation_error}), 400
        plate_read = read_plate_image(save_path, enforce_min_confidence=False)
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass

    if plate_read is None:
        return jsonify({
            "plate": None,
            "confidence": None,
            "raw_text": None,
            "source": None,
            "needs_review": True,
            "min_confidence": anpr_min_confidence(),
        })

    return jsonify({
        "plate": plate_read.plate,
        "confidence": plate_read.confidence,
        "raw_text": plate_read.raw_text,
        "source": plate_read.source,
        "needs_review": is_low_confidence(plate_read),
        "min_confidence": anpr_min_confidence(),
    })


@roles_required(*INSPECTION_REVIEWER_ROLES)
def update_inspection_review(inspection_id):
    """Record a human review decision and optional correction label."""
    inspection = db.get_or_404(Inspection, inspection_id)
    review_status = (request.form.get("review_status") or "").strip()
    if review_status not in VALID_REVIEW_STATUSES:
        flash("Choose a valid review status.", "error")
        return redirect(url_for("inspection_detail", inspection_id=inspection.id))

    review_notes = (request.form.get("review_notes") or "").strip()
    if len(review_notes) > MAX_REVIEW_NOTES_LENGTH:
        flash(f"Reviewer notes must be {MAX_REVIEW_NOTES_LENGTH} characters or fewer.", "error")
        return redirect(url_for("inspection_detail", inspection_id=inspection.id))

    correction_label = (request.form.get("correction_label") or "").strip().lower()
    if correction_label and correction_label not in CORRECTION_LABELS:
        flash("Choose a valid correction label.", "error")
        return redirect(url_for("inspection_detail", inspection_id=inspection.id))

    old_status = inspection.review_status
    old_correction_label = inspection.correction_label
    reviewer = g.current_user
    inspection.review_status = review_status
    inspection.review_notes = review_notes or None
    inspection.correction_label = correction_label or None
    inspection.reviewer_id = reviewer.id
    inspection.reviewed_at = datetime.now(timezone.utc)

    log_audit_event(
        "inspection.reviewed",
        entity_type="inspection",
        entity_id=inspection.id,
        details={
            "from_status": old_status,
            "to_status": review_status,
            "from_correction_label": old_correction_label,
            "to_correction_label": inspection.correction_label,
            "has_notes": bool(inspection.review_notes),
        },
    )
    db.session.commit()
    flash(f"Inspection #{inspection.id} review saved.", "success")
    return redirect(url_for("inspection_detail", inspection_id=inspection.id))


def save_history_filter():
    """Save the current history query string as a named filter for the user."""
    name = re.sub(r"\s+", " ", (request.form.get("name") or "").strip())
    if not name:
        flash("Enter a saved filter name.", "error")
        return redirect(url_for("history", **_non_empty_history_params()))
    if len(name) > 80:
        flash("Saved filter name must be 80 characters or fewer.", "error")
        return redirect(url_for("history", **_non_empty_history_params()))

    params = {
        key: value
        for key, value in request.form.items()
        if key in _history_filters() and value
    }
    saved_filter = SavedFilter.query.filter_by(
        user_id=g.current_user.id,
        page="history",
        name=name,
    ).first()
    if saved_filter is None:
        saved_filter = SavedFilter(user_id=g.current_user.id, page="history", name=name, params="{}")
        db.session.add(saved_filter)
    saved_filter.params = json.dumps(params, sort_keys=True)
    db.session.flush()
    log_audit_event(
        "saved_filter.saved",
        entity_type="saved_filter",
        entity_id=saved_filter.id,
        details={"page": "history", "name": name, "params": params},
    )
    db.session.commit()
    flash(f"Saved filter '{name}'.", "success")
    return redirect(url_for("history", **params))


def delete_history_filter(filter_id):
    saved_filter = db.get_or_404(SavedFilter, filter_id)
    if saved_filter.user_id != g.current_user.id:
        return Response("Not found", status=404)
    name = saved_filter.name
    db.session.delete(saved_filter)
    log_audit_event(
        "saved_filter.deleted",
        entity_type="saved_filter",
        entity_id=filter_id,
        details={"page": "history", "name": name},
    )
    db.session.commit()
    flash(f"Deleted saved filter '{name}'.", "success")
    return redirect(url_for("history"))


@roles_required(*INSPECTION_OPERATOR_ROLES)
def predict():
    """Accept an image upload, run inference, and save an inspection record."""
    if "image" not in request.files:
        flash("No image file uploaded.", "error")
        return redirect(url_for("new_inspection"))

    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        return form_error("Invalid file. Please upload a JPG, PNG, BMP, or WebP image.")

    plate, error = normalize_plate(request.form.get("plate", ""))
    if error:
        return form_error(error)
    location, error = clean_metadata_value(
        request.form.get("location", ""),
        max_length=200,
        field_name="Location",
        allow_empty=True,
    )
    if error:
        return form_error(error)
    camera, error = clean_metadata_value(
        request.form.get("camera", ""),
        max_length=20,
        field_name="Camera",
        uppercase=True,
        allow_empty=True,
    )
    if error:
        return form_error(error)
    location = location or "Unknown Location"
    location_ref, camera_ref = resolve_operational_context(location, camera)

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    save_path = os.path.join(upload_folder, unique_name)
    os.makedirs(upload_folder, exist_ok=True)
    file.save(save_path)

    validation_error = _validate_saved_image(save_path)
    if validation_error:
        os.remove(save_path)
        return form_error(validation_error)

    image_rel_path = f"uploads/{unique_name}"
    try:
        with open(save_path, "rb") as _fh:
            image_bytes = _fh.read()
    except OSError:
        image_bytes = None
    image_mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    image_checksum = sha256(image_bytes).hexdigest() if image_bytes else None
    duplicate_inspection = None
    if image_checksum:
        duplicate_inspection = (
            Inspection.query
            .filter_by(image_checksum=image_checksum)
            .order_by(Inspection.timestamp.desc())
            .first()
        )

    plate_source = "manual" if plate else None
    plate_confidence = None
    plate_raw_text = None
    if not plate:
        plate_read = read_plate_image(save_path, enforce_min_confidence=False)
        if plate_read:
            plate_confidence = plate_read.confidence
            plate_raw_text = plate_read.raw_text
            if is_low_confidence(plate_read):
                plate_source = f"{plate_read.source}_low_confidence"
                plate_raw_text = f"{plate_read.raw_text} | candidate: {plate_read.plate}"[:200]
            else:
                plate = plate_read.plate
                plate_source = plate_read.source
        else:
            plate_source = "ocr_failed"

    try:
        started_at = time.perf_counter()
        prediction = classify_tyre_image(save_path)
        inference_ms = int(round((time.perf_counter() - started_at) * 1000))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("ATIS inference error: %s", exc)
        flash("AI model inference failed. Please verify dependencies and model weights.", "error")
        return redirect(url_for("new_inspection"))

    status = prediction["status"]
    confidence = prediction["confidence"]
    defects_list = prediction["defects"]
    predicted_class = prediction["predicted_class"]
    model_path = prediction["model_path"]
    model_version = _model_fingerprint(model_path)
    bounding_boxes = prediction.get("boxes", [])

    defects_str = ",".join(defects_list) if defects_list else None
    stored_image = None
    if image_bytes:
        try:
            stored_image = store_image(image_bytes, filename=unique_name, mime=image_mime)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error("Image storage failed: %s", exc)
            flash("Could not persist uploaded image. Please try again.", "error")
            return redirect(url_for("new_inspection"))

    inspection = Inspection(
        timestamp=datetime.now(timezone.utc),
        plate=plate,
        location_id=location_ref.id if location_ref else None,
        camera_id=camera_ref.id if camera_ref else None,
        location=location,
        camera=camera,
        created_by_id=g.current_user.id,
        status=status,
        confidence=confidence,
        predicted_class=predicted_class,
        model_path=model_path,
        model_version=model_version,
        model_threshold=prediction.get("threshold"),
        low_confidence=bool(prediction.get("low_confidence")),
        inference_ms=inference_ms,
        defects=defects_str,
        plate_source=plate_source,
        plate_confidence=plate_confidence,
        plate_raw_text=plate_raw_text,
        image_path=image_rel_path,
        image_data=stored_image.data if stored_image else None,
        image_mime=stored_image.mime if stored_image else None,
        image_storage=stored_image.storage if stored_image else "disk",
        image_object_key=stored_image.object_key if stored_image else None,
        image_size=stored_image.size if stored_image else None,
        image_checksum=image_checksum,
        boxes=json.dumps(bounding_boxes) if bounding_boxes else None,
    )
    db.session.add(inspection)
    db.session.flush()
    sync_inspection_defects(
        inspection,
        defects_list,
        boxes=bounding_boxes,
        default_confidence=confidence,
        model_source=model_path,
    )

    log_audit_event(
        "inspection.created",
        entity_type="inspection",
        entity_id=inspection.id,
        details={
            "status": status,
            "confidence": confidence,
            "predicted_class": predicted_class,
            "defects": defects_list,
            "duplicate_of": duplicate_inspection.id if duplicate_inspection else None,
            "image_checksum": image_checksum,
            "plate": plate,
            "plate_source": plate_source,
            "plate_confidence": plate_confidence,
            "model_version": model_version,
            "model_threshold": prediction.get("threshold"),
            "inference_ms": inference_ms,
        },
    )

    if status == "unsafe" and predicted_class != "not_tyre":
        alert = Alert(
            inspection_id=inspection.id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(alert)
        db.session.flush()
        log_audit_event(
            "alert.created",
            entity_type="alert",
            entity_id=alert.id,
            details={"inspection_id": inspection.id, "source": "inspection_prediction"},
        )

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
            "model_version": model_version,
            "model_threshold": prediction.get("threshold"),
            "inference_ms": inference_ms,
            "plate": plate,
            "plate_source": plate_source,
            "plate_confidence": plate_confidence,
            "plate_raw_text": plate_raw_text,
            "image_url": url_for("inspection_image", inspection_id=inspection.id),
            "detail_url": url_for("inspection_detail", inspection_id=inspection.id),
            "dashboard_url": url_for("dashboard"),
            "duplicate_of": duplicate_inspection.id if duplicate_inspection else None,
        })

    if duplicate_inspection:
        flash(
            f"Inspection #{inspection.id} completed. Uploaded image matches inspection #{duplicate_inspection.id}.",
            "warning",
        )
        return redirect(url_for("inspection_detail", inspection_id=inspection.id))

    flash(
        f"Inspection #{inspection.id} completed - {predicted_class.upper()} ({confidence}%)",
        "success" if status == "safe" else "warning",
    )
    return redirect(url_for("inspection_detail", inspection_id=inspection.id))


def register_routes(app):
    app.add_url_rule("/history", "history", history)
    app.add_url_rule("/review/anpr", "anpr_review_queue", anpr_review_queue)
    app.add_url_rule("/history/saved-filters", "save_history_filter", save_history_filter, methods=["POST"])
    app.add_url_rule(
        "/history/saved-filters/<int:filter_id>/delete",
        "delete_history_filter",
        delete_history_filter,
        methods=["POST"],
    )
    app.add_url_rule("/inspection/<int:inspection_id>", "inspection_detail", inspection_detail)
    app.add_url_rule(
        "/inspection/<int:inspection_id>/compare/<int:other_id>",
        "duplicate_compare",
        duplicate_compare,
    )
    app.add_url_rule(
        "/inspection/<int:inspection_id>/review",
        "update_inspection_review",
        update_inspection_review,
        methods=["POST"],
    )
    app.add_url_rule("/media/inspection/<int:inspection_id>", "inspection_image", inspection_image)
    app.add_url_rule("/inspect", "new_inspection", new_inspection)
    app.add_url_rule("/api/anpr/preview", "anpr_preview", anpr_preview, methods=["POST"])
    app.add_url_rule("/predict", "predict", predict, methods=["POST"])
