"""Prometheus metrics endpoint (dependency-free).

Exposes a ``/metrics`` endpoint in the Prometheus text exposition format,
derived from the database so a scrape reflects real operational state
(inspection mix, pending alerts, recent unsafe rate, inference latency, async job
backlog). Hand-rolled rather than pulling in ``prometheus_client`` to keep the
pinned-dependency set unchanged.

Set ``ATIS_METRICS_TOKEN`` to require ``Authorization: Bearer <token>`` on the
endpoint; unset, it is open like ``/healthz`` (put it behind network policy).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from flask import Response, jsonify, request

from models import Alert, InferenceJob, Inspection, User, db


def _fmt(name: str, value, help_text: str, type_: str = "gauge", labels: dict | None = None) -> list[str]:
    label_str = ""
    if labels:
        label_str = "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
    return [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} {type_}",
        f"{name}{label_str} {value}",
    ]


def _collect() -> str:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    recent = (Inspection.timestamp >= since,)

    def count(model, *conditions):
        return db.session.scalar(
            db.select(db.func.count()).select_from(model).where(*conditions)
        ) or 0

    safe = count(Inspection, Inspection.status == "safe")
    unsafe = count(Inspection, Inspection.status == "unsafe")
    recent_total = count(Inspection, *recent)
    recent_unsafe = count(Inspection, *recent, Inspection.status == "unsafe")
    pending_alerts = count(Alert, Alert.status == "pending")
    active_users = count(User, User.is_active.is_(True))
    avg_ms = db.session.scalar(
        db.select(db.func.avg(Inspection.inference_ms)).where(*recent, Inspection.inference_ms.is_not(None))
    )

    lines: list[str] = []
    lines += _fmt("atis_up", 1, "Application is serving.")
    # One HELP/TYPE block, two labelled series (safe / unsafe).
    lines += _fmt("atis_inspections_total", safe, "Inspections by verdict.", "gauge", {"status": "safe"})
    lines += [f'atis_inspections_total{{status="unsafe"}} {unsafe}']
    lines += _fmt("atis_inspections_recent_total", recent_total, "Inspections in the last 24h.")
    lines += _fmt("atis_inspections_recent_unsafe_total", recent_unsafe, "Unsafe inspections in the last 24h.")
    lines += _fmt("atis_alerts_pending", pending_alerts, "Alerts awaiting acknowledgement.")
    lines += _fmt("atis_users_active", active_users, "Active user accounts.")
    lines += _fmt(
        "atis_inference_ms_avg_recent",
        round(float(avg_ms), 2) if avg_ms is not None else 0,
        "Average model inference time (ms) over the last 24h.",
    )

    # Async job backlog (only meaningful when async inference is enabled, but the
    # table always exists post-migration).
    job_help_emitted = False
    for status in ("queued", "running", "done", "error"):
        n = count(InferenceJob, InferenceJob.status == status)
        if not job_help_emitted:
            lines += ["# HELP atis_inference_jobs Background inference jobs by status.",
                      "# TYPE atis_inference_jobs gauge"]
            job_help_emitted = True
        lines += [f'atis_inference_jobs{{status="{status}"}} {n}']

    return "\n".join(lines) + "\n"


def register_metrics(flask_app):
    @flask_app.get("/metrics")
    def metrics():
        # Read per-request so the token can be set/rotated without a restart.
        token = os.environ.get("ATIS_METRICS_TOKEN")
        if token and request.headers.get("Authorization") != f"Bearer {token}":
            return jsonify({"error": "Unauthorized"}), 401
        return Response(_collect(), mimetype="text/plain; version=0.0.4; charset=utf-8")
