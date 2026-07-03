"""Structured defect taxonomy and inspection-defect persistence helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from models import DefectType, InspectionDefect, db


def display_defect_name(raw: str) -> str:
    """Normalize whitespace while preserving operator-facing capitalization."""
    return re.sub(r"\s+", " ", (raw or "").strip())


def normalized_defect_name(raw: str) -> str:
    return display_defect_name(raw).lower()


def get_or_create_defect_type(name: str) -> DefectType:
    """Return the canonical defect type row for a display name."""
    display_name = display_defect_name(name)
    normalized_name = normalized_defect_name(display_name)
    defect_type = DefectType.query.filter_by(normalized_name=normalized_name).first()
    if defect_type is not None:
        return defect_type

    defect_type = DefectType(
        name=display_name[:80],
        normalized_name=normalized_name[:80],
    )
    db.session.add(defect_type)
    db.session.flush()
    return defect_type


def _box_for_defect(defect_name: str, boxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalized_defect_name(defect_name)
    for box in boxes:
        label = normalized_defect_name(str(box.get("label") or box.get("predicted_class") or ""))
        if label == normalized:
            return box
    return boxes[0] if len(boxes) == 1 else None


def sync_inspection_defects(
    inspection,
    defects: list[str],
    *,
    boxes: list[dict[str, Any]] | None = None,
    default_confidence: int | None = None,
    model_source: str | None = None,
) -> list[InspectionDefect]:
    """Replace an inspection's structured defect rows from inference output."""
    inspection.inspection_defects.clear()
    boxes = boxes or []
    rows: list[InspectionDefect] = []
    seen: set[str] = set()

    for raw_defect in defects:
        name = display_defect_name(raw_defect)
        normalized = normalized_defect_name(name)
        if not name or normalized in seen:
            continue
        seen.add(normalized)

        box = _box_for_defect(name, boxes)
        bbox = box.get("bbox") if box else None
        row = InspectionDefect(
            inspection=inspection,
            defect_type=get_or_create_defect_type(name),
            severity=str(box.get("severity"))[:20] if box and box.get("severity") else None,
            confidence=int(box.get("confidence")) if box and box.get("confidence") is not None else default_confidence,
            bbox=json.dumps(bbox) if isinstance(bbox, list) else None,
            model_source=model_source,
        )
        db.session.add(row)
        rows.append(row)

    return rows
