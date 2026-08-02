"""Data-retention, erasure, and subject-access tests."""

from datetime import datetime, timedelta, timezone

from models import Alert, AuditEvent, Inspection, db
from services.retention import (
    cutoff_for,
    erase_plate_data,
    export_plate_data,
    purge_expired,
)


def _add_inspection(plate, *, days_old, status="unsafe", with_alert=False):
    timestamp = datetime.now(timezone.utc) - timedelta(days=days_old)
    inspection = Inspection(
        timestamp=timestamp,
        plate=plate,
        location="Retention Gate",
        status=status,
        confidence=90,
    )
    db.session.add(inspection)
    db.session.flush()
    if with_alert:
        db.session.add(Alert(inspection_id=inspection.id, status="pending", created_at=timestamp))
    db.session.commit()
    return inspection.id


def test_cutoff_disabled_when_days_zero_or_negative():
    assert cutoff_for(0) is None
    assert cutoff_for(-5) is None
    assert cutoff_for(30) is not None


def test_purge_dry_run_reports_without_deleting(app):
    with app.app_context():
        _add_inspection("OLD-0001", days_old=100, with_alert=True)
        _add_inspection("NEW-0001", days_old=1)

        summary = purge_expired(retention_days=30, audit_retention_days=0, dry_run=True)

        assert summary["inspections_deleted"] == 1
        assert summary["alerts_deleted"] == 1
        # Nothing actually removed on a dry run.
        assert Inspection.query.count() == 2
        assert Alert.query.count() == 1


def test_purge_apply_deletes_expired_and_cascades_alerts(app):
    with app.app_context():
        old_id = _add_inspection("OLD-0002", days_old=100, with_alert=True)
        _add_inspection("NEW-0002", days_old=1)

        summary = purge_expired(retention_days=30, audit_retention_days=0, dry_run=False)

        assert summary["inspections_deleted"] == 1
        assert db.session.get(Inspection, old_id) is None
        # The expired inspection's alert is gone; the recent inspection remains.
        assert Alert.query.count() == 0
        assert Inspection.query.count() == 1


def test_purge_audit_events_respects_separate_window(app):
    with app.app_context():
        db.session.add(AuditEvent(action="test.old", created_at=datetime.now(timezone.utc) - timedelta(days=400)))
        db.session.add(AuditEvent(action="test.new", created_at=datetime.now(timezone.utc) - timedelta(days=5)))
        db.session.commit()

        summary = purge_expired(retention_days=0, audit_retention_days=365, dry_run=False)

        assert summary["audit_events_deleted"] == 1
        assert AuditEvent.query.count() == 1


def test_export_plate_data_returns_all_records_case_insensitive(app):
    with app.app_context():
        _add_inspection("ABC-1234", days_old=10, with_alert=True)
        _add_inspection("ABC-1234", days_old=2)
        _add_inspection("OTHER-99", days_old=1)

        export = export_plate_data("abc-1234")

        assert export["plate"] == "ABC-1234"
        assert export["record_count"] == 2
        assert {r["plate"] for r in export["records"]} == {"ABC-1234"}
        assert export["records"][0]["alerts"]  # alert metadata is included


def test_erase_plate_data_removes_only_that_plate(app):
    with app.app_context():
        _add_inspection("ERASE-ME", days_old=10, with_alert=True)
        keep_id = _add_inspection("KEEP-ME", days_old=1)

        dry = erase_plate_data("erase-me", dry_run=True)
        assert dry["inspections_deleted"] == 1
        assert Inspection.query.count() == 2  # dry run changed nothing

        summary = erase_plate_data("erase-me", dry_run=False)
        assert summary["inspections_deleted"] == 1
        assert Inspection.query.filter_by(plate="ERASE-ME").count() == 0
        assert db.session.get(Inspection, keep_id) is not None
        assert Alert.query.count() == 0
