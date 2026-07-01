"""Inference guardrail tests."""

import numpy as np

import atis_inference


class _FakeConfidence:
    def item(self):
        return 0.99


class _FakeProbData:
    def tolist(self):
        return [0.99, 0.01]


class _FakeProbs:
    top1 = 0
    top1conf = _FakeConfidence()
    data = _FakeProbData()


class _FakeResult:
    names = {0: "normal", 1: "cracked"}
    probs = _FakeProbs()


class _FakeClassifier:
    def __call__(self, *_args, **_kwargs):
        return [_FakeResult()]


def test_blank_safe_prediction_is_reported_as_not_tyre(monkeypatch):
    monkeypatch.setattr(atis_inference, "load_classifier", lambda *_args, **_kwargs: _FakeClassifier())
    monkeypatch.setattr(atis_inference, "find_model_path", lambda: None)

    frame = np.full((224, 224, 3), 255, dtype=np.uint8)
    result = atis_inference.classify_tyre_frame(frame)

    assert result["status"] == "unsafe"
    assert result["predicted_class"] == "not_tyre"
    assert result["defects"] == ["Not a tyre"]
