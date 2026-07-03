"""Run ANPR against sample plate fixtures and print a compact tuning report."""

from __future__ import annotations

import argparse
from pathlib import Path

from services.anpr import anpr_min_confidence, is_low_confidence, read_plate_image


DEFAULT_SAMPLES = Path("tests/fixtures/anpr_samples")
EXPECTED = {
    "sample_plate_abc_1234.png": "ABC-1234",
    "sample_plate_lea_4455.png": "LEA-4455",
    "sample_plate_low_light_nha_908.png": "NHA-908",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_dir", nargs="?", default=DEFAULT_SAMPLES, type=Path)
    args = parser.parse_args()

    print(f"ANPR minimum confidence: {anpr_min_confidence()}%")
    print("file,expected,detected,confidence,state")
    failures = 0
    for image_path in sorted(args.sample_dir.glob("*.png")):
        expected = EXPECTED.get(image_path.name, "")
        result = read_plate_image(image_path, enforce_min_confidence=False)
        if result is None:
            detected = ""
            confidence = ""
            state = "no_read"
            failures += 1
        else:
            detected = result.plate
            confidence = "" if result.confidence is None else str(result.confidence)
            state = "low_confidence" if is_low_confidence(result) else "accepted"
            if expected and detected != expected:
                failures += 1
        print(f"{image_path.name},{expected},{detected},{confidence},{state}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
