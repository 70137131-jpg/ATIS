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
    assert card["held_out_test_metrics"]["status"] == "not_present_in_repo_artifacts"
