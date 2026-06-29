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


def _status_for_class(predicted_class: str) -> tuple[str, list[str]]:
    normalized = predicted_class.strip().lower()
    if normalized == "normal":
        return "safe", []
    if normalized == "cracked":
        return "unsafe", ["Cracking"]

    # Unknown classifier output should be reviewed instead of silently passed.
    return "unsafe", [f"Unexpected class: {predicted_class}"]


def classify_tyre_image(
    image_path: str | os.PathLike[str],
    model_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Classify a tire image and return normalized ATIS inspection fields."""
    model = load_classifier(model_path)
    results = model(str(image_path), verbose=False)
    if not results:
        raise RuntimeError("ATIS classifier returned no results.")

    result = results[0]
    if result.probs is None:
        raise RuntimeError("ATIS classifier did not return classification probabilities.")

    class_id = int(result.probs.top1)
    confidence = float(result.probs.top1conf.item()) * 100
    predicted_class = _class_name(result.names, class_id)
    status, defects = _status_for_class(predicted_class)

    return {
        "status": status,
        "confidence": max(0, min(100, int(round(confidence)))),
        "defects": defects,
        "predicted_class": predicted_class,
        "model_path": str(_classifier_path or find_model_path() or ""),
    }
