"""Report page, chart APIs, and PDF export routes."""

from flask import current_app, jsonify, render_template, send_file, session

from models import Inspection, db
from routes.common import REPORT_VIEWER_ROLES, parse_report_range, report_day_labels, roles_required
from services.audit import log_audit_event
from services.model_feedback import build_feedback_dataset_zip, default_feedback_filename
from services.reports import build_inspection_report_csv, build_inspection_report_pdf, defect_distribution_rows


@roles_required(*REPORT_VIEWER_ROLES)
def reports():
    return render_template("reports.html", user=session["user"], role=session["role"])


@roles_required(*REPORT_VIEWER_ROLES)
def api_safety_trend():
    start, end, _date_from, _date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    day_expr = db.func.date(Inspection.timestamp)
    rows = db.session.execute(
        db.select(day_expr, Inspection.status, db.func.count())
        .where(Inspection.timestamp >= start, Inspection.timestamp < end)
        .group_by(day_expr, Inspection.status)
    ).all()

    counts = {(str(day), status): int(count) for day, status, count in rows}
    day_keys, labels = report_day_labels(start, end)
    safe_counts = [counts.get((day, "safe"), 0) for day in day_keys]
    unsafe_counts = [
        sum(count for (row_day, status), count in counts.items() if row_day == day and status != "safe")
        for day in day_keys
    ]

    return jsonify({"labels": labels, "safe": safe_counts, "unsafe": unsafe_counts})


@roles_required(*REPORT_VIEWER_ROLES)
def api_defect_distribution():
    start, end, _date_from, _date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    sorted_defects = defect_distribution_rows(start, end)
    return jsonify({
        "labels": [item[0] for item in sorted_defects],
        "values": [item[1] for item in sorted_defects],
    })


@roles_required(*REPORT_VIEWER_ROLES)
def api_daily_summary():
    start, end, _date_from, _date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    day_expr = db.func.date(Inspection.timestamp)
    rows = db.session.execute(
        db.select(day_expr, Inspection.status, db.func.count())
        .where(Inspection.timestamp >= start, Inspection.timestamp < end)
        .group_by(day_expr, Inspection.status)
    ).all()

    counts = {(str(day), status): int(count) for day, status, count in rows}
    day_keys, labels = report_day_labels(start, end)
    total_counts = [
        sum(count for (row_day, _status), count in counts.items() if row_day == day)
        for day in day_keys
    ]
    unsafe_counts = [
        sum(count for (row_day, status), count in counts.items() if row_day == day and status == "unsafe")
        for day in day_keys
    ]

    return jsonify({"labels": labels, "total": total_counts, "unsafe": unsafe_counts})


@roles_required(*REPORT_VIEWER_ROLES)
def export_pdf():
    start, end, date_from, date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    inspections, total_matches, max_rows = _report_export_rows(start, end)
    buffer = build_inspection_report_pdf(
        inspections,
        start=start,
        end=end,
        total_matches=total_matches,
        max_rows=max_rows,
    )
    _log_report_export(
        "pdf",
        date_from=date_from,
        date_to=date_to,
        total_matches=total_matches,
        exported_rows=len(inspections),
        max_rows=max_rows,
    )

    filename = f"NHA_Report_{date_from}_to_{date_to}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


def _report_export_rows(start, end):
    report_filter = (
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
    )
    total_matches = db.session.scalar(
        db.select(db.func.count()).select_from(Inspection).where(*report_filter)
    ) or 0
    max_rows = current_app.config["REPORT_EXPORT_MAX_ROWS"]
    inspections = db.session.execute(
        db.select(Inspection)
        .where(*report_filter)
        .order_by(Inspection.timestamp.desc())
        .limit(max_rows)
    ).scalars().all()
    return inspections, total_matches, max_rows


def _log_report_export(format_name, *, date_from, date_to, total_matches, exported_rows, max_rows):
    log_audit_event(
        "report.exported",
        entity_type="report",
        details={
            "format": format_name,
            "date_from": date_from,
            "date_to": date_to,
            "total_matches": total_matches,
            "exported_rows": exported_rows,
            "max_rows": max_rows,
            "truncated": total_matches > exported_rows,
        },
    )
    db.session.commit()


@roles_required(*REPORT_VIEWER_ROLES)
def export_csv():
    start, end, date_from, date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    inspections, total_matches, max_rows = _report_export_rows(start, end)
    buffer = build_inspection_report_csv(inspections)
    _log_report_export(
        "csv",
        date_from=date_from,
        date_to=date_to,
        total_matches=total_matches,
        exported_rows=len(inspections),
        max_rows=max_rows,
    )

    filename = f"NHA_Report_{date_from}_to_{date_to}.csv"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv",
    )


@roles_required(*REPORT_VIEWER_ROLES)
def export_model_feedback():
    start, end, date_from, date_to, error = parse_report_range(current_app.config["REPORT_MAX_DAYS"])
    if error:
        return error

    max_rows = current_app.config["REPORT_EXPORT_MAX_ROWS"]
    feedback_filter = (
        Inspection.timestamp >= start,
        Inspection.timestamp < end,
        Inspection.correction_label.is_not(None),
        Inspection.correction_label != "",
    )
    total_matches = db.session.scalar(
        db.select(db.func.count()).select_from(Inspection).where(*feedback_filter)
    ) or 0
    inspections = db.session.execute(
        db.select(Inspection)
        .where(*feedback_filter)
        .order_by(Inspection.reviewed_at.desc().nullslast(), Inspection.timestamp.desc())
        .limit(max_rows)
    ).scalars().all()

    buffer, export_stats = build_feedback_dataset_zip(inspections)
    log_audit_event(
        "model_feedback.exported",
        entity_type="model_feedback",
        details={
            "date_from": date_from,
            "date_to": date_to,
            "total_matches": total_matches,
            "exported_rows": export_stats["included"],
            "skipped_missing_image": export_stats["skipped_missing_image"],
            "max_rows": max_rows,
            "truncated": total_matches > len(inspections),
        },
    )
    db.session.commit()

    return send_file(
        buffer,
        as_attachment=True,
        download_name=default_feedback_filename(date_from, date_to),
        mimetype="application/zip",
    )


def register_routes(app):
    app.add_url_rule("/reports", "reports", reports)
    app.add_url_rule("/api/reports/safety-trend", "api_safety_trend", api_safety_trend)
    app.add_url_rule("/api/reports/defect-distribution", "api_defect_distribution", api_defect_distribution)
    app.add_url_rule("/api/reports/daily-summary", "api_daily_summary", api_daily_summary)
    app.add_url_rule("/api/reports/export-pdf", "export_pdf", export_pdf)
    app.add_url_rule("/api/reports/export-csv", "export_csv", export_csv)
    app.add_url_rule("/api/model-feedback/export", "export_model_feedback", export_model_feedback)
