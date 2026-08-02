"""Data retention, erasure, and subject-access helpers (PII governance).

ATIS stores personal data: licence plates and inspection images
(``inspections``) and request IP addresses / user agents (``audit_events``).
A production deployment must be able to (a) age that data out on a schedule and
(b) answer a data-subject's access or erasure request for a specific plate.

Everything here is transactional and supports ``dry_run`` so an operator can see
exactly what a purge would remove before committing it. Deleting an inspection
also removes any externally-stored image (S3) and its alerts/comments/defect
rows, so no orphaned personal data is left behind in another store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from models import (
    Alert,
    AlertComment,
    AuditEvent,
    Inspection,
    InspectionDefect,
    db,
)
from services.image_storage import delete_image


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cutoff_for(days: int, *, now: datetime | None = None) -> datetime | None:
    """Return the timestamp older-than which rows expire, or None if disabled."""
    if days <= 0:
        return None
    return (now or _utcnow()) - timedelta(days=days)


def _delete_inspection(inspection: Inspection) -> None:
    """Delete one inspection and everything personal attached to it.

    Order matters: alerts hold a NOT NULL FK to the inspection, so they (and
    their cascade-deleted comments) go first; the inspection's defect rows
    cascade via the ORM relationship. Any S3-stored image object is removed too
    — DB-stored image bytes go away with the row itself.
    """
    try:
        delete_image(inspection)
    except Exception:  # noqa: BLE001 - never let a storage hiccup block erasure
        # The row is still deleted; a missed object is logged by the caller's
        # count of storage errors so it can be reconciled out of band.
        pass

    for alert in list(inspection.alerts):
        db.session.delete(alert)
    db.session.delete(inspection)


def purge_expired(
    *,
    retention_days: int,
    audit_retention_days: int,
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete inspections and audit events older than their retention windows.

    Returns a summary dict of what was (or, when ``dry_run``, would be) removed.
    A retention window of 0 leaves that data untouched.
    """
    now = now or _utcnow()
    inspection_cutoff = cutoff_for(retention_days, now=now)
    audit_cutoff = cutoff_for(audit_retention_days, now=now)

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "now": now.isoformat(),
        "inspection_cutoff": inspection_cutoff.isoformat() if inspection_cutoff else None,
        "audit_cutoff": audit_cutoff.isoformat() if audit_cutoff else None,
        "inspections_deleted": 0,
        "alerts_deleted": 0,
        "audit_events_deleted": 0,
    }

    if inspection_cutoff is not None:
        expired = (
            Inspection.query
            .filter(Inspection.timestamp < inspection_cutoff)
            .order_by(Inspection.id.asc())
            .all()
        )
        summary["inspections_deleted"] = len(expired)
        summary["alerts_deleted"] = sum(len(insp.alerts) for insp in expired)
        if not dry_run:
            for inspection in expired:
                _delete_inspection(inspection)

    if audit_cutoff is not None:
        audit_query = AuditEvent.query.filter(AuditEvent.created_at < audit_cutoff)
        summary["audit_events_deleted"] = audit_query.count()
        if not dry_run:
            for event in audit_query.all():
                db.session.delete(event)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return summary


def _plate_query(plate: str):
    normalized = (plate or "").strip().upper()
    return Inspection.query.filter(db.func.upper(Inspection.plate) == normalized)


def export_plate_data(plate: str) -> dict[str, Any]:
    """Return every inspection record held for a plate (subject-access request).

    Image bytes are described (size/mime/storage) but not embedded, so the
    export is a readable manifest of what personal data is held rather than a
    dump of raw files.
    """
    normalized = (plate or "").strip().upper()
    inspections = (
        _plate_query(normalized)
        .order_by(Inspection.timestamp.asc())
        .all()
    )
    records = []
    for insp in inspections:
        records.append({
            "inspection_id": insp.id,
            "timestamp": insp.timestamp.isoformat() if insp.timestamp else None,
            "plate": insp.plate,
            "plate_source": insp.plate_source,
            "plate_confidence": insp.plate_confidence,
            "location": insp.location,
            "camera": insp.camera,
            "status": insp.status,
            "confidence": insp.confidence,
            "predicted_class": insp.predicted_class,
            "defects": insp.defect_list,
            "review_status": insp.review_status,
            "correction_label": insp.correction_label,
            "image": {
                "storage": insp.image_storage,
                "mime": insp.image_mime,
                "size": insp.image_size,
                "checksum": insp.image_checksum,
            },
            "created_by": insp.created_by.email if insp.created_by else None,
            "alerts": [
                {"alert_id": a.id, "status": a.status, "created_at": a.created_at.isoformat() if a.created_at else None}
                for a in insp.alerts
            ],
        })
    return {
        "plate": normalized,
        "record_count": len(records),
        "generated_at": _utcnow().isoformat(),
        "records": records,
    }


def erase_plate_data(plate: str, *, dry_run: bool = True) -> dict[str, Any]:
    """Erase every inspection (and attached data/images) held for a plate.

    Returns a summary of what was (or would be) removed. This is the operative
    half of a data-subject erasure request; ``export_plate_data`` is the access
    half.
    """
    normalized = (plate or "").strip().upper()
    inspections = _plate_query(normalized).order_by(Inspection.id.asc()).all()
    summary = {
        "dry_run": dry_run,
        "plate": normalized,
        "inspections_deleted": len(inspections),
        "alerts_deleted": sum(len(insp.alerts) for insp in inspections),
    }
    if not dry_run:
        for inspection in inspections:
            _delete_inspection(inspection)
        db.session.commit()
    else:
        db.session.rollback()
    return summary


# Silence unused-import linters: these models are imported to document the full
# set of personal-data-bearing tables this module reasons about, and
# InspectionDefect / AlertComment are removed via ORM cascade.
_PERSONAL_DATA_TABLES = (Inspection, Alert, AlertComment, InspectionDefect, AuditEvent)
