"""Live model-monitoring metrics computed from stored inspections.

The curated-dataset metrics in ``model_card.json`` describe the classifier on a
held-out test split. They say nothing about how the model behaves on the real
checkpoint feed over time. This module derives operational health signals from
data the app already records on every inspection:

* prediction mix (safe / unsafe / not-tyre) and low-confidence rate
* a confidence distribution (drift in these often precedes accuracy drift)
* a *live accuracy proxy* from human review corrections — most importantly the
  live missed-defect rate (a reviewer relabels a "safe" tyre as cracked)

Run it from cron via ``flask atis-model-monitor`` to alert on drift; ``strict``
mode makes the command exit non-zero when a safety threshold is breached so a
scheduler can page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from models import Inspection, db

# A reviewer relabelling a passed tyre as cracked is the failure that matters
# most for a safety system; alert above this fraction of reviewed inspections.
DEFAULT_MAX_LIVE_MISSED_DEFECT_RATE = 0.02


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rate(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def compute_monitoring_metrics(
    *, window_days: int = 7, now: datetime | None = None
) -> dict[str, Any]:
    """Summarise model behaviour over the trailing ``window_days`` window."""
    now = now or _utcnow()
    start = now - timedelta(days=window_days)

    window = (Inspection.timestamp >= start, Inspection.timestamp <= now)

    def count(*conditions) -> int:
        return db.session.scalar(
            db.select(db.func.count()).select_from(Inspection).where(*window, *conditions)
        ) or 0

    total = count()
    safe = count(Inspection.status == "safe")
    unsafe = count(Inspection.status == "unsafe")
    not_tyre = count(Inspection.predicted_class == "not_tyre")
    low_confidence = count(Inspection.low_confidence.is_(True))

    avg_confidence = db.session.scalar(
        db.select(db.func.avg(Inspection.confidence)).where(*window)
    )
    avg_inference_ms = db.session.scalar(
        db.select(db.func.avg(Inspection.inference_ms)).where(
            *window, Inspection.inference_ms.is_not(None)
        )
    )

    # --- Live accuracy proxy from human review corrections ------------------
    reviewed = count(
        Inspection.correction_label.is_not(None),
        Inspection.correction_label != "",
    )
    # Model passed the tyre as safe, a reviewer relabelled it cracked: a real
    # missed defect that reached "safe" in production. This is the number to page on.
    live_missed_defects = count(
        Inspection.status == "safe",
        Inspection.correction_label == "cracked",
    )
    # Model flagged the tyre unsafe, a reviewer relabelled it plainly normal.
    live_false_flags = count(
        Inspection.status == "unsafe",
        Inspection.predicted_class == "normal",
        Inspection.correction_label == "normal",
    )

    return {
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "window_start": start.isoformat(),
        "volume": {
            "total": total,
            "safe": safe,
            "unsafe": unsafe,
            "not_tyre": not_tyre,
        },
        "rates": {
            "unsafe_rate": _rate(unsafe, total),
            "not_tyre_rate": _rate(not_tyre, total),
            "low_confidence_rate": _rate(low_confidence, total),
        },
        "confidence": {
            "avg": round(float(avg_confidence), 2) if avg_confidence is not None else None,
            "avg_inference_ms": int(round(avg_inference_ms)) if avg_inference_ms is not None else None,
        },
        "review": {
            "reviewed": reviewed,
            "reviewed_rate": _rate(reviewed, total),
            "live_missed_defects": live_missed_defects,
            "live_missed_defect_rate": _rate(live_missed_defects, reviewed),
            "live_false_flags": live_false_flags,
            "live_false_flag_rate": _rate(live_false_flags, reviewed),
        },
    }


def evaluate_health(
    metrics: dict[str, Any],
    *,
    max_live_missed_defect_rate: float = DEFAULT_MAX_LIVE_MISSED_DEFECT_RATE,
) -> dict[str, Any]:
    """Return pass/fail health verdicts derived from monitoring metrics."""
    missed_rate = metrics["review"]["live_missed_defect_rate"]
    breaches: list[str] = []
    if missed_rate is not None and missed_rate > max_live_missed_defect_rate:
        breaches.append(
            f"live missed-defect rate {missed_rate:.2%} exceeds "
            f"{max_live_missed_defect_rate:.2%}"
        )
    return {
        "ok": not breaches,
        "breaches": breaches,
        "max_live_missed_defect_rate": max_live_missed_defect_rate,
        "insufficient_review_data": metrics["review"]["reviewed"] == 0,
    }
