"""Shared ATIS inference helpers: crack **classifier** + crack **localizer**.

The trained model is a 2-class YOLOv11 classifier (``normal`` vs ``cracked``) that
gives the safety verdict. When a tyre is classified as cracked, a lightweight
classical-CV localizer (`_localize_cracks`) finds the crack region(s) in the image
and returns a bounding box around them, so the dashboard/live-feed overlay draws a
box **on the crack** rather than around the whole frame. The localizer is an
image-processing heuristic (black-hat morphology highlights the dark, thin crack
lines) — not a trained detector — so it needs no bounding-box training data.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_CANDIDATES = (
    "runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt",
    # 100-epoch weights committed via Git LFS land under a doubly-nested path.
    "runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt",
    "ATIS_Project/tyre_safety_model/weights/best.pt",
    "runs/classify/train/weights/best.pt",
)

# Confidence (top-1 probability) below which a 'normal' prediction is NOT
# auto-passed as safe. The model is a 2-class softmax, so the winning class is
# always >= 0.50; a meaningful threshold sits above that.
DEFAULT_CONF_THRESHOLD = 0.60
DEFAULT_OBJECT_CONF_THRESHOLD = 0.35

# Flat-frame gate defaults: a frame whose grayscale std-dev (contrast) or Canny
# edge-pixel fraction falls below these is rejected as "not a tyre" before the
# classifier verdict is trusted. Tunable per site — a dark or hazy toll-booth
# camera may need lower values to avoid rejecting genuine tyre frames.
DEFAULT_FLAT_CONTRAST_MIN = 10.0
DEFAULT_FLAT_EDGE_DENSITY_MIN = 0.003

OBJECT_MODEL_CANDIDATES = (
    "yolo26n.pt",
)

# Classifier outputs that mean "this tyre is cracked". Shared so the verdict
# mapping, the localizer trigger, and the alert rule in routes/ all agree.
CRACKED_CLASS_NAMES = {"crack", "cracked", "cracking"}

VEHICLE_CLASSES = {"bicycle", "car", "motorcycle", "bus", "truck"}
NON_TYRE_OBJECT_CLASSES = {
    "person", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear",
    "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase",
    "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
}

_classifier_model = None
_classifier_path: Path | None = None
_object_model = None
_object_model_path: Path | None = None

# The models are process-wide singletons, but the app serves them from several
# threads at once (gunicorn runs 1 worker x GUNICORN_THREADS, and the async
# inference pool adds ATIS_INFERENCE_WORKERS more). An Ultralytics model reuses
# one internal predictor and mutates its state in place during a call, so two
# concurrent predicts on the same object can interleave and cross-contaminate
# results — one request receiving another's verdict. Both locks below prevent
# that:
#   _model_load_lock  — only one thread constructs a model (a cold race would
#                       otherwise build two and hold double the weights in RAM).
#   _predict_lock     — serializes every model call. Inference is CPU-bound and
#                       already the bottleneck, so this costs little throughput,
#                       and it stops 4 request threads x torch's own intra-op
#                       threads from oversubscribing a small instance. It is an
#                       RLock so a future nested call degrades to slow rather
#                       than deadlocking a worker.
_model_load_lock = threading.Lock()
_predict_lock = threading.RLock()


def candidate_model_paths() -> list[Path]:
    """Return model paths to try, honoring ATIS_MODEL_PATH first."""
    candidates: list[Path] = []
    env_path = os.environ.get("ATIS_MODEL_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    for relative_path in DEFAULT_MODEL_CANDIDATES:
        candidates.append(PROJECT_ROOT / relative_path)

    return candidates


def find_model_path() -> Path | None:
    """Return the first available trained classifier path."""
    for path in candidate_model_paths():
        if path.exists():
            return path
    return None


def get_conf_threshold() -> float:
    """Confidence threshold (fraction 0-1) below which a 'normal' tire is not
    auto-passed. Read from ATIS_CONF_THRESHOLD; tolerates percent form (e.g. 60)
    and falls back to the default on a missing/invalid value."""
    raw = os.environ.get("ATIS_CONF_THRESHOLD")
    if not raw:
        return DEFAULT_CONF_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CONF_THRESHOLD
    if value > 1:  # tolerate "60" meaning 60%
        value = value / 100
    return min(max(value, 0.0), 1.0)


def get_object_conf_threshold() -> float:
    """Confidence threshold for the optional non-tyre object gate."""
    raw = os.environ.get("ATIS_OBJECT_CONF_THRESHOLD")
    if not raw:
        return DEFAULT_OBJECT_CONF_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_OBJECT_CONF_THRESHOLD
    if value > 1:
        value = value / 100
    return min(max(value, 0.0), 1.0)


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back on missing/invalid."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_flat_contrast_min() -> float:
    """Grayscale std-dev below which a frame is rejected as blank/flat
    (env ATIS_FLAT_CONTRAST_MIN)."""
    return max(_env_float("ATIS_FLAT_CONTRAST_MIN", DEFAULT_FLAT_CONTRAST_MIN), 0.0)


def get_flat_edge_density_min() -> float:
    """Canny edge-pixel fraction below which a frame is rejected as featureless
    (env ATIS_FLAT_EDGE_DENSITY_MIN)."""
    value = _env_float("ATIS_FLAT_EDGE_DENSITY_MIN", DEFAULT_FLAT_EDGE_DENSITY_MIN)
    return min(max(value, 0.0), 1.0)


def tyre_gate_enabled() -> bool:
    """Return whether non-tyre rejection is enabled."""
    raw = os.environ.get("ATIS_TYRE_GATE", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def localize_enabled() -> bool:
    """Return whether crack localization (box drawing) is enabled."""
    raw = os.environ.get("ATIS_LOCALIZE", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def find_object_model_path() -> Path | None:
    """Return the optional COCO detector used to reject obvious non-tyre frames."""
    env_path = os.environ.get("ATIS_OBJECT_MODEL_PATH")
    candidates = [Path(env_path).expanduser()] if env_path else []
    candidates.extend(PROJECT_ROOT / relative_path for relative_path in OBJECT_MODEL_CANDIDATES)
    for path in candidates:
        if path.exists():
            return path
    return None


def load_classifier(model_path: str | os.PathLike[str] | None = None) -> Any:
    """Lazy-load the trained Ultralytics classification model."""
    global _classifier_model, _classifier_path

    resolved_path = Path(model_path).expanduser() if model_path else find_model_path()
    if resolved_path is None:
        searched = ", ".join(str(path) for path in candidate_model_paths())
        raise FileNotFoundError(f"ATIS model weights not found. Searched: {searched}")

    resolved_path = resolved_path.resolve()
    # Fast path: already loaded. Reading the globals is atomic, so a hit needs
    # no lock; only construction does.
    if _classifier_model is not None and _classifier_path == resolved_path:
        return _classifier_model

    with _model_load_lock:
        if _classifier_model is None or _classifier_path != resolved_path:
            from ultralytics import YOLO

            _classifier_model = YOLO(str(resolved_path))
            _classifier_path = resolved_path

    return _classifier_model


def load_object_detector() -> Any | None:
    """Lazy-load the optional COCO detector for non-tyre rejection."""
    global _object_model, _object_model_path

    resolved_path = find_object_model_path()
    if resolved_path is None:
        return None

    resolved_path = resolved_path.resolve()
    if _object_model is not None and _object_model_path == resolved_path:
        return _object_model

    with _model_load_lock:
        if _object_model is None or _object_model_path != resolved_path:
            from ultralytics import YOLO

            _object_model = YOLO(str(resolved_path))
            _object_model_path = resolved_path

    return _object_model


def _class_name(names: Any, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, (list, tuple)) and class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def _status_for_class(
    predicted_class: str, confidence: float, threshold: float
) -> tuple[str, list[str]]:
    """Map a predicted class to a safety status using an asymmetric, fail-safe
    confidence gate: a tire is only passed as 'safe' when the model is confident
    it is 'normal'. ``confidence`` is the top-1 probability as a fraction (0-1)."""
    normalized = predicted_class.strip().lower()

    # A cracked tire is unsafe regardless of confidence — never gated.
    if normalized in CRACKED_CLASS_NAMES:
        return "unsafe", ["Cracking"]

    if normalized == "normal":
        if confidence >= threshold:
            return "safe", []
        # Low-confidence 'normal' is not waved through; flag for manual review.
        return "unsafe", ["Low-confidence normal — manual review"]

    # Unknown classifier output should be reviewed instead of silently passed.
    return "unsafe", [f"Unexpected class: {predicted_class}"]


def _frame_array(model_input: Any) -> Any | None:
    """Return an OpenCV/Numpy image array (BGR) for the localizer / non-tyre checks."""
    try:
        import cv2
        import numpy as np
    except Exception:  # noqa: BLE001 - gate is best-effort
        return None

    if isinstance(model_input, (str, os.PathLike)):
        frame = cv2.imread(str(model_input))
        return frame if frame is not None else None

    if isinstance(model_input, np.ndarray):
        return model_input

    return None


def _localize_cracks(model_input: Any, confidence: int, max_boxes: int = 2) -> list[dict[str, Any]]:
    """Find crack region(s) in the image and return normalized boxes focused on
    them. Uses black-hat morphology to highlight the dark, thin crack lines, then
    boxes the strongest elongated responses. Returns [] if localization is off or
    the image can't be read; always returns at least one box (peak response) when
    the tyre is cracked so the overlay points at the defect."""
    if not localize_enabled():
        return []

    frame = _frame_array(model_input)
    if frame is None:
        return []

    try:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        h, w = gray.shape[:2]
        if h == 0 or w == 0:
            return []

        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

        # Black-hat: bright where there are dark, thin structures (cracks).
        bh_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        blackhat = cv2.morphologyEx(eq, cv2.MORPH_BLACKHAT, bh_kernel)

        _, mask = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)

        # Local crack density: the average crack-pixel fraction inside a moderate
        # window centered at each pixel. The densest windows are where cracking
        # concentrates, so boxing them keeps the box focused on the crack(s) —
        # tight on a lone crack, and on the worst area when cracking is widespread.
        maskf = (mask > 0).astype(np.float32)
        win_w = max(16, int(w * 0.30))
        win_h = max(16, int(h * 0.30))
        density = cv2.boxFilter(maskf, ddepth=-1, ksize=(win_w, win_h), normalize=True)

        def _norm_box(x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
            return {
                "label": "Crack",
                # The confidence is the *classifier's* verdict for the image;
                # the box position comes from the classical-CV localizer.
                # "source" makes that distinction visible to consumers so a
                # heuristic box is never mistaken for a trained detection.
                "confidence": int(confidence),
                "severity": "High",
                "source": "heuristic",
                "bbox": [
                    round(float(x1) / w, 4), round(float(y1) / h, 4),
                    round(float(x2) / w, 4), round(float(y2) / h, 4),
                ],
            }

        boxes: list[dict[str, Any]] = []
        for _ in range(max_boxes):
            _minv, maxv, _minl, (cx, cy) = cv2.minMaxLoc(density)
            if maxv < 0.03:  # too little crack density here to call it a defect
                break
            x1, y1 = max(0, cx - win_w // 2), max(0, cy - win_h // 2)
            x2, y2 = min(w, cx + win_w // 2), min(h, cy + win_h // 2)
            boxes.append(_norm_box(x1, y1, x2, y2))
            # Suppress this window so the next pick is a different crack cluster.
            density[max(0, cy - win_h):min(h, cy + win_h),
                    max(0, cx - win_w):min(w, cx + win_w)] = 0.0

        # Fallback: cracked class but no dense region → point a focused box at the
        # single strongest crack response so the overlay still marks the defect.
        if not boxes:
            _minv, _maxv, _minl, (px, py) = cv2.minMaxLoc(blackhat)
            bw, bh = max(12, int(w * 0.20)), max(12, int(h * 0.20))
            x1, y1 = max(0, px - bw // 2), max(0, py - bh // 2)
            boxes = [_norm_box(x1, y1, min(w, x1 + bw), min(h, y1 + bh))]
        return boxes
    except Exception:  # noqa: BLE001 - localization is best-effort, never fatal
        return []


def _flat_frame_reason(model_input: Any, frame: Any = None) -> str | None:
    """Reject blank/flat frames that the classifier otherwise over-passes.

    ``frame`` is an already-decoded array; pass it to avoid re-reading the image.
    """
    if frame is None:
        frame = _frame_array(model_input)
    if frame is None:
        return None

    try:
        import cv2
        import numpy as np

        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        if gray.size == 0:
            return "Not a tyre"

        contrast = float(np.std(gray))
        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size)

        if contrast < get_flat_contrast_min() or edge_density < get_flat_edge_density_min():
            return "Not a tyre"
    except Exception:  # noqa: BLE001 - never let the gate break inference
        return None

    return None


def _detected_non_tyre_reason(model_input: Any, frame: Any = None) -> str | None:
    """Use a generic object detector to reject obvious non-tyre subjects.

    ``frame`` is an already-decoded array; when given it is fed to the detector
    instead of the path so the image is not read from disk a second time.
    """
    detector = load_object_detector()
    if detector is None:
        return None

    try:
        threshold = get_object_conf_threshold()
        detector_input = model_input if frame is None else frame
        # Hold the lock across the call *and* the tensor reads below: the
        # Results objects borrow buffers from the shared predictor, so they are
        # only safe to touch before another thread starts the next predict.
        with _predict_lock:
            results = detector(detector_input, imgsz=320, conf=threshold, verbose=False)
            if not results:
                return None

            names = results[0].names
            boxes = getattr(results[0], "boxes", None)
            if boxes is None or boxes.cls is None or boxes.conf is None:
                return None

            detections: list[tuple[str, float]] = [
                (_class_name(names, int(class_id)).strip().lower(), float(conf))
                for class_id, conf in zip(boxes.cls.tolist(), boxes.conf.tolist())
            ]

        if any(name in VEHICLE_CLASSES for name, conf in detections if conf >= threshold):
            return None

        non_tyre_hits = [
            (name, conf)
            for name, conf in detections
            if conf >= threshold and name in NON_TYRE_OBJECT_CLASSES
        ]
        if not non_tyre_hits:
            return None

        name, _conf = max(non_tyre_hits, key=lambda item: item[1])
        return f"Not a tyre — detected {name}"
    except Exception:  # noqa: BLE001 - fall back to classifier if detector fails
        return None


def _non_tyre_reason(model_input: Any) -> str | None:
    """Return a reason when the input should not be treated as a tyre."""
    if not tyre_gate_enabled():
        return None
    # Decode once and share it with both checks. The gate now runs on every
    # prediction rather than only on 'safe' ones, so this keeps the added cost
    # to one detector pass instead of two extra image reads.
    frame = _frame_array(model_input)
    return (
        _flat_frame_reason(model_input, frame)
        or _detected_non_tyre_reason(model_input, frame)
    )


def _not_tyre_result(
    reason: str, *, model_path: str = "", classifier_class: str | None = None
) -> dict[str, Any]:
    """Build the verdict for a frame the tyre gate rejected.

    ``classifier_class`` records what the classifier called the frame before the
    gate overrode it, so a consumer can tell "blank frame the model called
    normal" apart from "the model called this cracked and the gate disagreed" —
    the latter is a conflict a human still needs to see.
    """
    return {
        "status": "unsafe",
        "confidence": 0,
        "defects": [reason or "Not a tyre"],
        "predicted_class": "not_tyre",
        "classifier_class": classifier_class,
        "threshold": round(get_conf_threshold() * 100),
        "low_confidence": False,
        "boxes": [],
        "bounding_boxes": [],
        "model_path": model_path,
    }


def _classify_model_input(
    model_input: Any,
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    model = load_classifier(model_path)
    # Hold the lock across the predict *and* the reads off the Results object,
    # which borrows buffers from the shared predictor. Everything after this
    # block is plain Python scalars and is safe to run concurrently.
    with _predict_lock:
        results = model(model_input, verbose=False)
        if not results:
            raise RuntimeError("ATIS classifier returned no results.")

        result = results[0]
        if result.probs is None:
            raise RuntimeError("ATIS classifier did not return classification probabilities.")

        class_id = int(result.probs.top1)
        conf_fraction = float(result.probs.top1conf.item())
        predicted_class = _class_name(result.names, class_id)

    threshold = get_conf_threshold()
    confidence = max(0, min(100, int(round(conf_fraction * 100))))
    resolved_model = str(_classifier_path or find_model_path() or "")

    # The non-tyre gate runs before the verdict is trusted, in *either*
    # direction. Gating only the 'safe' branch left the opposite hole wide open:
    # a wall, a person, or a blank frame that the classifier happens to call
    # 'cracked' was reported as a cracked tyre and raised a real defect alert.
    # A frame that is not a tyre cannot be a cracked tyre either way.
    reason = _non_tyre_reason(model_input)
    if reason:
        return _not_tyre_result(
            reason, model_path=resolved_model, classifier_class=predicted_class
        )

    status, defects = _status_for_class(predicted_class, conf_fraction, threshold)

    # Localize the crack so the overlay box lands on the defect, not the frame.
    is_cracked = predicted_class.strip().lower() in CRACKED_CLASS_NAMES
    boxes = _localize_cracks(model_input, confidence) if is_cracked else []

    return {
        "status": status,
        "confidence": confidence,
        "defects": defects,
        "predicted_class": predicted_class,
        "classifier_class": predicted_class,
        "threshold": round(threshold * 100),
        "low_confidence": status == "unsafe" and predicted_class.strip().lower() == "normal",
        "boxes": boxes,
        "bounding_boxes": boxes,
        "model_path": resolved_model,
    }


def classify_tyre_image(
    image_path: str | os.PathLike[str],
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Classify a tire image path and localize any crack; returns ATIS fields."""
    return _classify_model_input(str(image_path), model_path)


def classify_tyre_frame(
    frame: Any,
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Classify an in-memory OpenCV/Numpy frame or crop and localize any crack."""
    return _classify_model_input(frame, model_path)
