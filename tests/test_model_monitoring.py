"""Live model-monitoring metric tests."""

from datetime import datetime, timedelta, timezone

from models import Inspection, db
from services.model_monitoring import compute_monitoring_metrics, evaluate_health


def _add(status, *, predicted_class, days_old=1, low_confidence=False, correction_label=None):
    timestamp = datetime.now(timezone.utc) - timedelta(days=days_old)
    db.session.add(
        Inspection(
            timestamp=timestamp,
            plate="MON-0001",
            location="Monitor Gate",
            status=status,
            confidence=88,
            predicted_class=predicted_class,
            low_confidence=low_confidence,
            correction_label=correction_label,
        )
    )
    db.session.commit()


def test_metrics_summarise_prediction_mix(app):
    with app.app_context():
        _add("safe", predicted_class="normal")
        _add("unsafe", predicted_class="cracked")
        _add("unsafe", predicted_class="not_tyre")

        metrics = compute_monitoring_metrics(window_days=7)

        assert metrics["volume"]["total"] == 3
        assert metrics["volume"]["safe"] == 1
        assert metrics["volume"]["unsafe"] == 2
        assert metrics["volume"]["not_tyre"] == 1
        assert metrics["rates"]["not_tyre_rate"] == round(1 / 3, 4)


def test_window_excludes_older_rows(app):
    with app.app_context():
        _add("safe", predicted_class="normal", days_old=1)
        _add("safe", predicted_class="normal", days_old=90)

        metrics = compute_monitoring_metrics(window_days=7)

        assert metrics["volume"]["total"] == 1


def test_live_missed_defect_breaches_health(app):
    with app.app_context():
        # Reviewer relabelled a passed tyre as cracked: a live missed defect.
        _add("safe", predicted_class="normal", correction_label="cracked")
        _add("safe", predicted_class="normal", correction_label="normal")

        metrics = compute_monitoring_metrics(window_days=7)
        assert metrics["review"]["reviewed"] == 2
        assert metrics["review"]["live_missed_defects"] == 1
        assert metrics["review"]["live_missed_defect_rate"] == 0.5

        health = evaluate_health(metrics, max_live_missed_defect_rate=0.02)
        assert health["ok"] is False
        assert health["breaches"]


def test_health_ok_when_no_review_data(app):
    with app.app_context():
        _add("safe", predicted_class="normal")

        health = evaluate_health(compute_monitoring_metrics(window_days=7))
        assert health["ok"] is True
        assert health["insufficient_review_data"] is True
