"""Model card integrity tests."""

import json
from pathlib import Path


MODEL_CARD = Path(
    "runs/classify/runs/classify/ATIS_Project/tyre_safety_model/model_card.json"
)


def test_model_card_records_current_classifier_decision():
    card = json.loads(MODEL_CARD.read_text())

    assert card["model"]["task"] == "image classification"
    assert card["model"]["classes"] == ["normal", "cracked"]
    assert card["inference_policy"]["default_ATIS_CONF_THRESHOLD"] == 0.60
    assert card["architecture_decision"]["decision"] == (
        "Keep classifier plus heuristic localizer for the current product path."
    )
    assert card["localization"]["not_a_trained_detector"] is True


def test_model_card_records_held_out_test_metrics():
    """Held-out test evidence must be present and internally consistent."""
    card = json.loads(MODEL_CARD.read_text())

    assert card["held_out_test_metrics"]["status"] == "recorded"
    metrics = card["test_metrics"]
    assert 0.0 < metrics["accuracy"] <= 1.0
    for cls in ("normal", "cracked"):
        assert 0.0 < metrics["per_class"][cls]["recall"] <= 1.0
        assert metrics["per_class"][cls]["support"] > 0
    # The safety numbers must mirror the per-class recalls they derive from.
    safety = metrics["safety_argmax"]
    assert abs(safety["missed_defect_rate"] - (1 - metrics["per_class"]["cracked"]["recall"])) < 1e-9
    assert abs(safety["good_flagged_rate"] - (1 - metrics["per_class"]["normal"]["recall"])) < 1e-9
    # The shipped default threshold must be at least the swept minimum cutoff.
    assert card["inference_policy"]["default_ATIS_CONF_THRESHOLD"] >= metrics["chosen_threshold"]
