"""Live camera page and frame-analysis API routes."""

from __future__ import annotations

from flask import current_app, jsonify, render_template, request, session

from atis_inference import classify_tyre_frame
from routes.common import INSPECTION_OPERATOR_ROLES, roles_required


@roles_required(*INSPECTION_OPERATOR_ROLES)
def live_feed():
    """Render the browser-camera inspection UI."""
    return render_template(
        "live_feed.html",
        user=session["user"],
        role=session["role"],
    )


@roles_required(*INSPECTION_OPERATOR_ROLES)
def live_analyze():
    """Classify a single frame captured by the operator's browser camera."""
    file = request.files.get("frame")
    if file is None:
        return jsonify({"error": "no frame provided"}), 400

    import cv2
    import numpy as np

    max_bytes = current_app.config["LIVE_FRAME_MAX_BYTES"]
    frame_bytes = file.read(max_bytes + 1)
    if not frame_bytes:
        return jsonify({"error": "empty frame"}), 400
    if len(frame_bytes) > max_bytes:
        return jsonify({"error": "frame too large"}), 413

    buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "could not decode frame"}), 400
    height, width = frame.shape[:2]
    max_pixels = current_app.config["LIVE_FRAME_MAX_PIXELS"]
    if height * width > max_pixels:
        return jsonify({"error": "frame dimensions too large"}), 413

    try:
        prediction = classify_tyre_frame(frame)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("Live analyze inference failed: %s", exc)
        return jsonify({"error": "inference failed"}), 500

    return jsonify({
        key: prediction[key]
        for key in (
            "status", "confidence", "defects",
            "predicted_class", "threshold", "low_confidence",
        )
    } | {
        "boxes": prediction.get("boxes", []),
        "bounding_boxes": prediction.get("bounding_boxes", []),
    })


def register_routes(app, limiter):
    app.add_url_rule("/live", "live_feed", live_feed)
    app.add_url_rule(
        "/api/live/analyze",
        "live_analyze",
        limiter.limit("60 per minute")(live_analyze),
        methods=["POST"],
    )
