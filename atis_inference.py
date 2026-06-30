"""Shared ATIS classifier inference helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_CANDIDATES = (
    "runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt",
    "ATIS_Project/tyre_safety_model/weights/best.pt",
    "runs/classify/train/weights/best.pt",
)

# Confidence (top-1 probability) below which a 'normal' prediction is NOT
# auto-passed as safe. The model is a 2-class softmax, so the winning class is
# always >= 0.50; a meaningful threshold sits above that.
DEFAULT_CONF_THRESHOLD = 0.60

_classifier_model = None
_classifier_path: Path | None = None


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


def load_classifier(model_path: str | os.PathLike[str] | None = None) -> Any:
    """Lazy-load the trained Ultralytics classification model."""
    global _classifier_model, _classifier_path

    resolved_path = Path(model_path).expanduser() if model_path else find_model_path()
    if resolved_path is None:
        searched = ", ".join(str(path) for path in candidate_model_paths())
        raise FileNotFoundError(f"ATIS model weights not found. Searched: {searched}")

    resolved_path = resolved_path.resolve()
    if _classifier_model is None or _classifier_path != resolved_path:
        from ultralytics import YOLO

        _classifier_model = YOLO(str(resolved_path))
        _classifier_path = resolved_path

    return _classifier_model


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

    # Defect classes are unsafe regardless of confidence — never gated.
    if normalized in {"crack", "cracked", "cracking"}:
        return "unsafe", ["Cracking"]
    if normalized in {"bulge", "bulged", "sidewall_bulge", "sidewall bulge"}:
        return "unsafe", ["Bulge"]

    if normalized == "normal":
        if confidence >= threshold:
            return "safe", []
        # Low-confidence 'normal' is not waved through; flag for manual review.
        return "unsafe", ["Low-confidence normal — manual review"]

    # Unknown classifier output should be reviewed instead of silently passed.
    return "unsafe", [f"Unexpected class: {predicted_class}"]


def _classify_model_input(
    model_input: Any,
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    model = load_classifier(model_path)
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
    status, defects = _status_for_class(predicted_class, conf_fraction, threshold)

    # Full per-class probabilities for transparency/audit (e.g. operator review).
    prob_vector = result.probs.data.tolist()
    class_probs = {
        _class_name(result.names, i).strip().lower(): float(prob_vector[i])
        for i in range(len(prob_vector))
    }

    return {
        "status": status,
        "confidence": max(0, min(100, int(round(conf_fraction * 100)))),
        "defects": defects,
        "predicted_class": predicted_class,
        "threshold": round(threshold * 100),
        "low_confidence": status == "unsafe" and predicted_class.strip().lower() == "normal",
        "prob_normal": round(class_probs.get("normal", 0.0) * 100),
        "prob_cracked": round(class_probs.get("cracked", 0.0) * 100),
        "model_path": str(_classifier_path or find_model_path() or ""),
    }


def classify_tyre_image(
    image_path: str | os.PathLike[str],
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Classify a tire image path and return normalized ATIS inspection fields."""
    return _classify_model_input(str(image_path), model_path)


def classify_tyre_frame(
    frame: Any,
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Classify an in-memory OpenCV/Numpy frame or crop."""
    return _classify_model_input(frame, model_path)
