"""Classifier verdict + crack-localizer inference tests (model mocked).

The YOLO classifier is faked so these exercise the class->status mapping and the
box wiring without loading weights. One test runs the real `_localize_cracks`
image-processing localizer on a sample tyre photo.
"""

import os

import numpy as np

import atis_inference

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


class _FakeConf:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class _FakeProbData:
    def __init__(self, data):
        self.data = data

    def tolist(self):
        return self.data


class _FakeProbs:
    def __init__(self, top1, conf, probs):
        self.top1 = top1
        self.top1conf = _FakeConf(conf)
        self.data = _FakeProbData(probs)


class _FakeResult:
    def __init__(self, names, top1, conf, probs):
        self.names = names
        self.probs = _FakeProbs(top1, conf, probs)


def _classifier(names, top1, conf, probs):
    result = _FakeResult(names, top1, conf, probs)

    class _C:
        def __call__(self, *_a, **_k):
            return [result]

    return _C()


NAMES = {0: "normal", 1: "cracked"}
FRAME = np.zeros((64, 64, 3), dtype=np.uint8)


def _use(monkeypatch, top1, conf, probs, *, gate=False, localize=None):
    monkeypatch.setattr(
        atis_inference, "load_classifier",
        lambda *_a, **_k: _classifier(NAMES, top1, conf, probs),
    )
    monkeypatch.setattr(atis_inference, "find_model_path", lambda: None)
    if not gate:
        monkeypatch.setattr(atis_inference, "_non_tyre_reason", lambda *_a, **_k: None)
    if localize is not None:
        monkeypatch.setattr(atis_inference, "_localize_cracks", localize)


def test_cracked_is_unsafe_and_carries_localized_box(monkeypatch):
    fixed_box = [{"label": "Crack", "confidence": 90, "severity": "High",
                  "bbox": [0.2, 0.3, 0.5, 0.7]}]
    _use(monkeypatch, top1=1, conf=0.90, probs=[0.10, 0.90],
         localize=lambda *_a, **_k: fixed_box)
    result = atis_inference.classify_tyre_frame(FRAME)

    assert result["status"] == "unsafe"
    assert result["defects"] == ["Cracking"]
    assert result["boxes"] == fixed_box
    assert result["bounding_boxes"] == fixed_box


def test_confident_normal_is_safe_with_no_box(monkeypatch):
    _use(monkeypatch, top1=0, conf=0.95, probs=[0.95, 0.05])
    result = atis_inference.classify_tyre_frame(FRAME)

    assert result["status"] == "safe"
    assert result["defects"] == []
    assert result["boxes"] == []


def test_ultralytics_classification_result_with_list_names_is_parsed(monkeypatch):
    _use(monkeypatch, top1=1, conf=0.88, probs=[0.12, 0.88],
         localize=lambda *_a, **_k: [])
    monkeypatch.setattr(
        atis_inference,
        "load_classifier",
        lambda *_a, **_k: _classifier(["normal", "cracked"], 1, 0.88, [0.12, 0.88]),
    )

    result = atis_inference.classify_tyre_frame(FRAME)

    assert result["predicted_class"] == "cracked"
    assert result["status"] == "unsafe"
    assert result["confidence"] == 88
    assert result["threshold"] == 60


def test_low_confidence_normal_is_flagged_for_review(monkeypatch):
    _use(monkeypatch, top1=0, conf=0.52, probs=[0.52, 0.48])  # below 0.60 default
    result = atis_inference.classify_tyre_frame(FRAME)

    # Still withheld from passing (fail-safe), but it is not crack evidence.
    assert result["status"] == "unsafe"
    assert result["outcome"] == "needs_review"
    assert result["low_confidence"] is True
    assert result["defects"] == ["Low-confidence normal — manual review"]
    assert result["boxes"] == []


def test_outcome_splits_three_ways_while_status_stays_binary(monkeypatch):
    """`outcome` carries the real distinction; `status` keeps its old meaning.

    Reports, metrics and dashboards read `status`, so its safe/unsafe values
    must be exactly what they were before the split.
    """
    _use(monkeypatch, top1=0, conf=0.95, probs=[0.95, 0.05])
    confident_normal = atis_inference.classify_tyre_frame(FRAME)
    assert (confident_normal["status"], confident_normal["outcome"]) == ("safe", "safe")

    _use(monkeypatch, top1=0, conf=0.52, probs=[0.52, 0.48])
    unsure_normal = atis_inference.classify_tyre_frame(FRAME)
    assert (unsure_normal["status"], unsure_normal["outcome"]) == ("unsafe", "needs_review")

    _use(monkeypatch, top1=1, conf=0.90, probs=[0.10, 0.90], localize=lambda *_a, **_k: [])
    cracked = atis_inference.classify_tyre_frame(FRAME)
    assert (cracked["status"], cracked["outcome"]) == ("unsafe", "unsafe")


def test_unexpected_class_is_review_not_a_defect(monkeypatch):
    """An unrecognised class is the model failing to answer, not a crack."""
    monkeypatch.setattr(
        atis_inference, "load_classifier",
        lambda *_a, **_k: _classifier({0: "sidewall_bulge"}, 0, 0.99, [0.99]),
    )
    monkeypatch.setattr(atis_inference, "find_model_path", lambda: None)
    monkeypatch.setattr(atis_inference, "_non_tyre_reason", lambda *_a, **_k: None)

    result = atis_inference.classify_tyre_frame(FRAME)
    assert result["status"] == "unsafe"  # never passed
    assert result["outcome"] == "needs_review"
    assert result["defects"] == ["Unexpected class: sidewall_bulge"]


def test_classifier_parser_rejects_empty_ultralytics_results(monkeypatch):
    class _EmptyClassifier:
        def __call__(self, *_a, **_k):
            return []

    monkeypatch.setattr(atis_inference, "load_classifier", lambda *_a, **_k: _EmptyClassifier())

    import pytest
    with pytest.raises(RuntimeError, match="returned no results"):
        atis_inference.classify_tyre_frame(FRAME)


def test_classifier_parser_rejects_missing_probs(monkeypatch):
    class _ResultWithoutProbs:
        names = {0: "normal", 1: "cracked"}
        probs = None

    class _Classifier:
        def __call__(self, *_a, **_k):
            return [_ResultWithoutProbs()]

    monkeypatch.setattr(atis_inference, "load_classifier", lambda *_a, **_k: _Classifier())

    import pytest
    with pytest.raises(RuntimeError, match="classification probabilities"):
        atis_inference.classify_tyre_frame(FRAME)


def test_blank_frame_is_reported_as_not_tyre(monkeypatch):
    # Classifier says normal, but the flat-frame gate rejects a blank image.
    _use(monkeypatch, top1=0, conf=0.99, probs=[0.99, 0.01], gate=True)
    blank = np.full((224, 224, 3), 255, dtype=np.uint8)
    result = atis_inference.classify_tyre_frame(blank)

    assert result["status"] == "unsafe"
    assert result["predicted_class"] == "not_tyre"
    assert result["defects"] == ["Not a tyre"]
    assert result["classifier_class"] == "normal"
    assert result["outcome"] == "needs_review"


def test_non_tyre_frame_called_cracked_is_still_gated(monkeypatch):
    """The gate applies to a 'cracked' verdict too, not only to 'safe'.

    Gating only the safe branch meant a blank frame the classifier happened to
    call cracked was reported as a cracked tyre and raised a defect alert.
    """
    _use(monkeypatch, top1=1, conf=0.93, probs=[0.07, 0.93], gate=True)
    blank = np.full((224, 224, 3), 255, dtype=np.uint8)
    result = atis_inference.classify_tyre_frame(blank)

    assert result["predicted_class"] == "not_tyre"
    assert result["defects"] == ["Not a tyre"]
    assert result["boxes"] == []
    # The overridden classifier call is preserved so the conflict stays visible,
    # and it keeps a defect outcome — the gate may have misjudged a real crack.
    assert result["classifier_class"] == "cracked"
    assert result["outcome"] == "unsafe"


def test_gate_does_not_run_when_disabled(monkeypatch):
    """ATIS_TYRE_GATE=0 leaves the classifier verdict untouched in both directions."""
    monkeypatch.setenv("ATIS_TYRE_GATE", "0")
    blank = np.full((224, 224, 3), 255, dtype=np.uint8)

    _use(monkeypatch, top1=1, conf=0.93, probs=[0.07, 0.93], gate=True,
         localize=lambda *_a, **_k: [])
    assert atis_inference.classify_tyre_frame(blank)["predicted_class"] == "cracked"

    _use(monkeypatch, top1=0, conf=0.99, probs=[0.99, 0.01], gate=True)
    assert atis_inference.classify_tyre_frame(blank)["status"] == "safe"


def test_flat_frame_thresholds_are_env_tunable(monkeypatch):
    """Site operators can relax the flat-frame gate for dark/hazy cameras."""
    blank = np.full((224, 224, 3), 255, dtype=np.uint8)

    # Default thresholds reject a blank frame...
    assert atis_inference._flat_frame_reason(blank) == "Not a tyre"

    # ...but zeroed thresholds accept it (contrast 0 >= 0, density 0 >= 0).
    monkeypatch.setenv("ATIS_FLAT_CONTRAST_MIN", "0")
    monkeypatch.setenv("ATIS_FLAT_EDGE_DENSITY_MIN", "0")
    assert atis_inference._flat_frame_reason(blank) is None

    # Invalid values fall back to the defaults.
    monkeypatch.setenv("ATIS_FLAT_CONTRAST_MIN", "not-a-number")
    monkeypatch.setenv("ATIS_FLAT_EDGE_DENSITY_MIN", "")
    assert atis_inference.get_flat_contrast_min() == atis_inference.DEFAULT_FLAT_CONTRAST_MIN
    assert (
        atis_inference.get_flat_edge_density_min()
        == atis_inference.DEFAULT_FLAT_EDGE_DENSITY_MIN
    )


def test_concurrent_predicts_never_overlap_on_the_shared_model(monkeypatch):
    """The process-wide model is served from several threads at once.

    Ultralytics reuses one internal predictor and mutates it during a call, so
    overlapping predicts can cross-contaminate results — one request receiving
    another's verdict. _predict_lock must serialize them.
    """
    import threading
    import time

    counter_lock = threading.Lock()
    active = 0
    overlaps = []

    class _SlowClassifier:
        def __call__(self, *_a, **_k):
            nonlocal active
            with counter_lock:
                active += 1
                if active > 1:
                    overlaps.append(active)
            time.sleep(0.02)  # widen the window an unlocked predict would race in
            with counter_lock:
                active -= 1
            return [_FakeResult(NAMES, 0, 0.95, [0.95, 0.05])]

    monkeypatch.setattr(atis_inference, "load_classifier", lambda *_a, **_k: _SlowClassifier())
    monkeypatch.setattr(atis_inference, "find_model_path", lambda: None)
    monkeypatch.setattr(atis_inference, "_non_tyre_reason", lambda *_a, **_k: None)

    errors = []
    verdicts = []

    def _run():
        try:
            verdicts.append(atis_inference.classify_tyre_frame(FRAME)["status"])
        except Exception as exc:  # noqa: BLE001 - surface it as a failure below
            errors.append(exc)

    threads = [threading.Thread(target=_run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads), "predict lock deadlocked"
    assert not errors, f"concurrent predicts raised: {errors}"
    assert overlaps == [], f"predicts overlapped on the shared model: {overlaps}"
    assert verdicts == ["safe"] * 8


def test_localizer_boxes_are_marked_heuristic(monkeypatch):
    """Every localizer box carries source=heuristic so consumers can tell it
    apart from a trained detection."""
    frame = np.random.default_rng(7).integers(0, 255, (128, 128, 3), dtype=np.uint8)
    boxes = atis_inference._localize_cracks(frame, confidence=77)
    assert boxes, "localizer should always return at least one box"
    for box in boxes:
        assert box["source"] == "heuristic"


class _FakeList:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class _FakeBoxes:
    def __init__(self, cls, conf):
        self.cls = _FakeList(cls)
        self.conf = _FakeList(conf)


class _FakeDetectionResult:
    def __init__(self, names, cls, conf):
        self.names = names
        self.boxes = _FakeBoxes(cls, conf)


def test_object_detector_fake_ultralytics_result_rejects_non_tyre(monkeypatch):
    class _Detector:
        def __call__(self, *_a, **_k):
            return [_FakeDetectionResult({0: "person", 1: "car"}, [0], [0.91])]

    monkeypatch.setattr(atis_inference, "load_object_detector", lambda: _Detector())
    monkeypatch.setenv("ATIS_OBJECT_CONF_THRESHOLD", "0.35")

    assert atis_inference._detected_non_tyre_reason(FRAME) == "Not a tyre — detected person"


def test_object_detector_fake_ultralytics_vehicle_result_allows_frame(monkeypatch):
    class _Detector:
        def __call__(self, *_a, **_k):
            return [_FakeDetectionResult({0: "person", 2: "truck"}, [0, 2], [0.92, 0.80])]

    monkeypatch.setattr(atis_inference, "load_object_detector", lambda: _Detector())
    monkeypatch.setenv("ATIS_OBJECT_CONF_THRESHOLD", "0.35")

    assert atis_inference._detected_non_tyre_reason(FRAME) is None


def test_localizer_boxes_a_crack_region_on_a_real_image():
    """The real black-hat localizer returns an in-bounds box on a tyre photo."""
    import pytest

    sample = os.path.join(BASE_DIR, "tyre3.jpg")
    if not os.path.exists(sample):
        pytest.skip("sample tyre image not present")
    if atis_inference._frame_array(sample) is None:
        pytest.skip("OpenCV not available")

    boxes = atis_inference._localize_cracks(sample, confidence=88)
    assert len(boxes) >= 1
    for box in boxes:
        x1, y1, x2, y2 = box["bbox"]
        assert 0.0 <= x1 < x2 <= 1.0
        assert 0.0 <= y1 < y2 <= 1.0
        assert box["label"] == "Crack"
