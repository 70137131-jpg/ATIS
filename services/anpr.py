"""Automatic number plate recognition helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MIN_CONFIDENCE = 55


@dataclass(frozen=True)
class PlateReadResult:
    plate: str
    confidence: int | None
    raw_text: str
    source: str


def anpr_enabled() -> bool:
    raw = os.environ.get("ATIS_ANPR_ENABLED", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def anpr_min_confidence() -> int:
    raw = os.environ.get("ATIS_ANPR_MIN_CONFIDENCE")
    if raw is None:
        return DEFAULT_MIN_CONFIDENCE
    try:
        return min(max(int(float(raw)), 0), 100)
    except ValueError:
        return DEFAULT_MIN_CONFIDENCE


def normalize_plate_text(raw: str | None) -> str | None:
    """Normalize OCR/manual plate text into the app's plate format."""
    value = re.sub(r"[\s_]+", "-", (raw or "").strip().upper())
    value = re.sub(r"[^A-Z0-9-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value or len(value) > 20:
        return None
    return value


def _candidate_tokens(raw_text: str) -> list[str]:
    text = (raw_text or "").upper()
    text = text.replace("—", "-").replace("–", "-")
    rough_tokens = re.findall(r"[A-Z0-9][A-Z0-9\s_-]{2,18}[A-Z0-9]", text)
    candidates: list[str] = []
    for token in rough_tokens:
        normalized = normalize_plate_text(token)
        if normalized:
            candidates.append(normalized)
    compact = normalize_plate_text(text)
    if compact:
        candidates.append(compact)
    return list(dict.fromkeys(candidates))


def _plate_score(candidate: str, confidence: int | None) -> float:
    score = float(confidence or 0)
    length = len(candidate.replace("-", ""))
    has_letter = bool(re.search(r"[A-Z]", candidate))
    has_digit = bool(re.search(r"\d", candidate))
    if 5 <= length <= 10:
        score += 20
    if has_letter and has_digit:
        score += 20
    if "-" in candidate:
        score += 5
    if length < 4 or length > 12:
        score -= 30
    return score


def best_plate_candidate(raw_text: str, confidence: int | None = None) -> PlateReadResult | None:
    candidates = _candidate_tokens(raw_text)
    if not candidates:
        return None
    plate = max(candidates, key=lambda candidate: _plate_score(candidate, confidence))
    if _plate_score(plate, confidence) < 20:
        return None
    return PlateReadResult(
        plate=plate,
        confidence=confidence,
        raw_text=(raw_text or "").strip()[:200],
        source="ocr",
    )


def _tesseract_data_to_text_and_conf(data: dict[str, Any]) -> tuple[str, int | None]:
    words: list[str] = []
    confidences: list[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", []), strict=False):
        cleaned = (text or "").strip()
        if cleaned:
            words.append(cleaned)
        try:
            conf_value = float(conf)
        except (TypeError, ValueError):
            continue
        if conf_value >= 0:
            confidences.append(conf_value)
    avg_confidence = int(round(sum(confidences) / len(confidences))) if confidences else None
    return " ".join(words), avg_confidence


def _preprocessed_images(image_path: str | os.PathLike[str]):
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    return [image, gray, clahe, otsu, adaptive]


def is_low_confidence(result: PlateReadResult | None) -> bool:
    return bool(result and result.confidence is not None and result.confidence < anpr_min_confidence())


def read_plate_image(
    image_path: str | os.PathLike[str],
    *,
    enforce_min_confidence: bool = True,
) -> PlateReadResult | None:
    """Read a license plate from an image using optional Tesseract OCR."""
    if not anpr_enabled() or not image_path or not Path(image_path).exists():
        return None

    try:
        import pytesseract
        from pytesseract import Output
    except Exception:  # noqa: BLE001 - ANPR is optional/best-effort
        return None

    config = (
        "--oem 3 --psm 6 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- "
        "-c load_system_dawg=0 -c load_freq_dawg=0"
    )
    best: PlateReadResult | None = None
    for image in _preprocessed_images(image_path):
        try:
            data = pytesseract.image_to_data(image, output_type=Output.DICT, config=config)
        except Exception:  # noqa: BLE001 - missing binary/bad OCR should not block inspection
            return None
        raw_text, confidence = _tesseract_data_to_text_and_conf(data)
        candidate = best_plate_candidate(raw_text, confidence)
        if candidate is None:
            continue
        candidate = PlateReadResult(
            plate=candidate.plate,
            confidence=candidate.confidence,
            raw_text=candidate.raw_text,
            source="tesseract",
        )
        if best is None or _plate_score(candidate.plate, candidate.confidence) > _plate_score(best.plate, best.confidence):
            best = candidate

    if best is None:
        return None
    if enforce_min_confidence and is_low_confidence(best):
        return None
    return best
