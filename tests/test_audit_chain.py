"""Tamper-evident audit-log hash-chain tests."""

from models import AuditEvent, db
from services.audit import GENESIS_HASH, log_audit_event, verify_audit_chain


def test_events_are_chained(app):
    with app.app_context():
        log_audit_event("test.one", entity_type="thing", entity_id=1)
        log_audit_event("test.two", entity_type="thing", entity_id=2)
        db.session.commit()

        events = AuditEvent.query.order_by(AuditEvent.id.asc()).all()
        assert len(events) == 2
        # First event links to genesis; second links to the first.
        assert events[0].prev_hash == GENESIS_HASH
        assert events[0].entry_hash
        assert events[1].prev_hash == events[0].entry_hash
        assert events[1].entry_hash != events[0].entry_hash


def test_verify_passes_on_clean_chain(app):
    with app.app_context():
        for i in range(5):
            log_audit_event("test.event", entity_type="thing", entity_id=i)
        db.session.commit()

        report = verify_audit_chain()
        assert report["ok"] is True
        assert report["checked"] == 5
        assert report["first_broken_id"] is None


def test_verify_detects_tampered_content(app):
    with app.app_context():
        log_audit_event("test.a", entity_type="thing", entity_id=1)
        log_audit_event("test.b", entity_type="thing", entity_id=2)
        log_audit_event("test.c", entity_type="thing", entity_id=3)
        db.session.commit()

        # Tamper with the middle row's stored details without recomputing hashes.
        victim = AuditEvent.query.order_by(AuditEvent.id.asc()).all()[1]
        victim.details = '{"tampered": true}'
        db.session.commit()

        report = verify_audit_chain()
        assert report["ok"] is False
        assert report["first_broken_id"] == victim.id
        assert "entry_hash" in report["reason"]


def test_verify_detects_deleted_row(app):
    with app.app_context():
        log_audit_event("test.a", entity_type="thing", entity_id=1)
        log_audit_event("test.b", entity_type="thing", entity_id=2)
        log_audit_event("test.c", entity_type="thing", entity_id=3)
        db.session.commit()

        # Delete the middle row: the third row's prev_hash now points at a hash
        # that no longer precedes it, breaking the chain link.
        middle = AuditEvent.query.order_by(AuditEvent.id.asc()).all()[1]
        db.session.delete(middle)
        db.session.commit()

        report = verify_audit_chain()
        assert report["ok"] is False
        assert "prev_hash" in report["reason"]


def test_legacy_rows_without_hashes_are_counted_not_failed(app):
    with app.app_context():
        # Simulate a pre-chain legacy row (NULL hashes).
        db.session.add(AuditEvent(action="legacy.event"))
        db.session.commit()
        log_audit_event("test.new", entity_type="thing", entity_id=1)
        db.session.commit()

        report = verify_audit_chain()
        assert report["ok"] is True
        assert report["legacy_unchained"] == 1
        assert report["checked"] == 1
