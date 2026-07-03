"""Report export tests."""

from datetime import datetime

from models import AuditEvent, DefectType, Inspection, InspectionDefect, User, db


def _auth_as(client, app, email, role):
    with app.app_context():
        user = User(email=email, role=role)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user"] = email
        sess["role"] = role


def test_pdf_export_is_bounded_for_large_ranges(client, app):
    _auth_as(client, app, "reporter@example.com", "Supervisor")
    app.config["REPORT_EXPORT_MAX_ROWS"] = 2

    with app.app_context():
        for idx in range(5):
            db.session.add(
                Inspection(
                    plate=f"RPT-{idx:04d}",
                    location="Report Gate",
                    status="safe",
                    confidence=90,
                )
            )
        db.session.commit()

    resp = client.get("/api/reports/export-pdf?from=2026-01-01&to=2026-01-31")

    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.headers["Content-Disposition"].startswith("attachment;")


def test_csv_export_includes_review_and_model_metadata(client, app):
    _auth_as(client, app, "csv-reporter@example.com", "Supervisor")
    with app.app_context():
        inspection = Inspection(
            timestamp=datetime(2026, 1, 5, 9),
            plate="CSV-101",
            location="CSV Gate",
            camera="CAM-CSV",
            status="unsafe",
            confidence=81,
            defects="Cracking",
            review_status="false_positive",
            correction_label="normal",
            predicted_class="cracked",
            model_version="abc123",
            model_threshold=60,
            inference_ms=144,
        )
        db.session.add(inspection)
        db.session.commit()

    resp = client.get("/api/reports/export-csv?from=2026-01-01&to=2026-01-31")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    csv_text = resp.data.decode("utf-8-sig")
    assert "CSV-101" in csv_text
    assert "false_positive" in csv_text
    assert "normal" in csv_text
    assert "cracked" in csv_text
    assert "abc123" in csv_text
    with app.app_context():
        event = AuditEvent.query.filter_by(action="report.exported").one()
        assert event.details_dict["format"] == "csv"
        assert event.details_dict["exported_rows"] == 1


def test_report_apis_return_exact_aggregates(client, app):
    _auth_as(client, app, "analytics@example.com", "Supervisor")
    with app.app_context():
        rows = [
            Inspection(timestamp=datetime(2026, 1, 1, 9), location="A", status="safe", confidence=90),
            Inspection(timestamp=datetime(2026, 1, 1, 10), location="A", status="unsafe", confidence=80, defects="Cracking"),
            Inspection(timestamp=datetime(2026, 1, 2, 9), location="B", status="unsafe", confidence=75, defects="Cracking,Low-confidence normal"),
        ]
        db.session.add_all(rows)
        db.session.commit()

    trend = client.get("/api/reports/safety-trend?from=2026-01-01&to=2026-01-02").get_json()
    assert trend == {
        "labels": ["Jan 01", "Jan 02"],
        "safe": [1, 0],
        "unsafe": [1, 1],
    }

    daily = client.get("/api/reports/daily-summary?from=2026-01-01&to=2026-01-02").get_json()
    assert daily == {
        "labels": ["Jan 01", "Jan 02"],
        "total": [2, 1],
        "unsafe": [1, 1],
    }

    defects = client.get("/api/reports/defect-distribution?from=2026-01-01&to=2026-01-02").get_json()
    assert defects == {
        "labels": ["Cracking", "Low-confidence normal"],
        "values": [2, 1],
    }


def test_report_apis_return_exact_empty_outputs(client, app):
    _auth_as(client, app, "empty-analytics@example.com", "Supervisor")

    trend = client.get("/api/reports/safety-trend?from=2026-03-01&to=2026-03-03").get_json()
    daily = client.get("/api/reports/daily-summary?from=2026-03-01&to=2026-03-03").get_json()
    defects = client.get("/api/reports/defect-distribution?from=2026-03-01&to=2026-03-03").get_json()

    assert trend == {
        "labels": ["Mar 01", "Mar 02", "Mar 03"],
        "safe": [0, 0, 0],
        "unsafe": [0, 0, 0],
    }
    assert daily == {
        "labels": ["Mar 01", "Mar 02", "Mar 03"],
        "total": [0, 0, 0],
        "unsafe": [0, 0, 0],
    }
    assert defects == {"labels": [], "values": []}


def test_defect_distribution_trims_tokens_and_sorts_ties(client, app):
    _auth_as(client, app, "defect-cleanup@example.com", "Supervisor")
    with app.app_context():
        rows = [
            Inspection(timestamp=datetime(2026, 4, 1, 9), location="A", status="unsafe", confidence=80, defects=" Crack , Bulge,,"),
            Inspection(timestamp=datetime(2026, 4, 1, 10), location="A", status="unsafe", confidence=80, defects="Bulge, Crack"),
            Inspection(timestamp=datetime(2026, 4, 1, 11), location="A", status="unsafe", confidence=80, defects="Sidewall"),
        ]
        db.session.add_all(rows)
        db.session.commit()

    defects = client.get("/api/reports/defect-distribution?from=2026-04-01&to=2026-04-01").get_json()

    assert defects == {
        "labels": ["Bulge", "Crack", "Sidewall"],
        "values": [2, 2, 1],
    }


def test_defect_distribution_uses_normalized_defect_rows(client, app):
    _auth_as(client, app, "normalized-defects@example.com", "Supervisor")
    with app.app_context():
        crack = DefectType(name="Crack", normalized_name="crack")
        bulge = DefectType(name="Bulge", normalized_name="bulge")
        db.session.add_all([crack, bulge])
        db.session.flush()
        inspections = [
            Inspection(timestamp=datetime(2026, 5, 1, 9), location="A", status="unsafe", confidence=80, defects="Legacy ignored"),
            Inspection(timestamp=datetime(2026, 5, 1, 10), location="A", status="unsafe", confidence=80),
            Inspection(timestamp=datetime(2026, 5, 1, 11), location="A", status="unsafe", confidence=80),
        ]
        db.session.add_all(inspections)
        db.session.flush()
        db.session.add_all([
            InspectionDefect(inspection_id=inspections[0].id, defect_type_id=crack.id, confidence=91),
            InspectionDefect(inspection_id=inspections[1].id, defect_type_id=crack.id, confidence=88),
            InspectionDefect(inspection_id=inspections[2].id, defect_type_id=bulge.id, confidence=70),
        ])
        db.session.commit()

    defects = client.get("/api/reports/defect-distribution?from=2026-05-01&to=2026-05-01").get_json()

    assert defects == {
        "labels": ["Crack", "Bulge"],
        "values": [2, 1],
    }


def test_report_range_is_capped(client, app):
    _auth_as(client, app, "range@example.com", "Supervisor")
    app.config["REPORT_MAX_DAYS"] = 7

    resp = client.get("/api/reports/safety-trend?from=2026-01-01&to=2026-02-01")

    assert resp.status_code == 400
    assert "cannot exceed 7 days" in resp.get_json()["error"]


def test_report_range_rejects_invalid_and_reversed_ranges(client, app):
    _auth_as(client, app, "range-errors@example.com", "Supervisor")

    invalid = client.get("/api/reports/daily-summary?from=2026-01-xx&to=2026-01-02")
    reversed_range = client.get("/api/reports/daily-summary?from=2026-01-03&to=2026-01-02")

    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "Invalid date format. Use YYYY-MM-DD."
    assert reversed_range.status_code == 400
    assert reversed_range.get_json()["error"] == "Date range must end after it starts."
