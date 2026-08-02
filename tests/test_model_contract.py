"""End-to-end model contract test against the REAL trained weights.

Every other inference test mocks the YOLO model to exercise the decision logic.
This one loads the actual committed ``best.pt`` and runs a real image through the
app's ``classify_tyre_image`` so the model->app contract (result schema, value
ranges) is verified for real. It skips cleanly when the weights are absent or
still a Git-LFS pointer stub (e.g. a lightweight CI checkout), so it never turns
a missing large file into a spurious failure.
"""

from pathlib import Path

import pytest

import atis_inference

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _weights_are_real() -> bool:
    path = atis_inference.find_model_path()
    if path is None or not path.exists():
        return False
    # Git-LFS pointer stubs are small text files beginning with this line.
    try:
        head = path.read_bytes()[:64]
    except OSError:
        return False
    return b"git-lfs" not in head and len(head) >= 64


pytestmark = pytest.mark.skipif(
    not _weights_are_real(),
    reason="Real classifier weights not present (LFS stub or missing); skipping contract test.",
)


@pytest.fixture(scope="module")
def sample_image(tmp_path_factory):
    """A valid, textured JPEG the real classifier can decode and run on.

    The verdict is irrelevant here — this test checks the result *contract*, not
    correctness — so a deterministic textured image is enough and keeps the test
    independent of any committed upload files.
    """
    pytest.importorskip("ultralytics")
    from PIL import Image

    try:
        import numpy as np

        rng = np.random.default_rng(0)
        array = rng.integers(0, 255, size=(224, 224, 3), dtype="uint8")
        image = Image.fromarray(array, "RGB")
    except Exception:  # noqa: BLE001 - numpy optional; fall back to a plain image
        image = Image.new("RGB", (224, 224), (128, 128, 128))

    path = tmp_path_factory.mktemp("contract") / "sample.jpg"
    image.save(path, format="JPEG")
    return str(path)


def test_classify_real_image_returns_valid_contract(sample_image):
    result = atis_inference.classify_tyre_image(sample_image)

    # Schema: every field the app persists / returns must be present.
    for key in (
        "status",
        "confidence",
        "defects",
        "predicted_class",
        "threshold",
        "low_confidence",
        "boxes",
        "model_path",
    ):
        assert key in result, f"missing key: {key}"

    assert result["status"] in {"safe", "unsafe"}
    assert 0 <= result["confidence"] <= 100
    assert 0 <= result["threshold"] <= 100
    assert isinstance(result["defects"], list)
    assert isinstance(result["boxes"], list)
    assert isinstance(result["low_confidence"], bool)
    # A safe verdict must never carry defects; an unsafe one must explain itself.
    if result["status"] == "safe":
        assert result["defects"] == []
    else:
        assert result["defects"]


def test_localizer_boxes_are_normalized_and_labelled(sample_image):
    """If any crack box is returned, it must be normalized (0-1) and flagged heuristic."""
    result = atis_inference.classify_tyre_image(sample_image)
    for box in result["boxes"]:
        assert box.get("source") == "heuristic"
        bbox = box.get("bbox")
        assert isinstance(bbox, list) and len(bbox) == 4
        assert all(0.0 <= coord <= 1.0 for coord in bbox)
