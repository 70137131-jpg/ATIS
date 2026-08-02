"""
field_validation.py — Validate the ATIS classifier on REAL checkpoint footage.

The curated held-out metrics in model_card.json come from studio/web imagery and
do not prove the model works on the target cameras. This harness runs the exact
same honest, safety-focused evaluation as evaluate_model.py, but against a
field dataset you collect from the deployment site, and records the result in the
model card under a separate ``field_metrics`` key so it is never confused with
the curated numbers.

Collect the dataset per docs/field_validation_protocol.md, then lay it out as:

    <field_dir>/
        normal/    *.jpg   (confirmed-good tyres photographed at the site)
        cracked/   *.jpg   (confirmed-cracked tyres)

Run:

    python3 field_validation.py --field-dir /path/to/field_dataset

The report is printed and merged into model_card.json. The classifier's
production decision threshold (ATIS_CONF_THRESHOLD, default 0.60) is used for the
safety numbers so the metrics reflect what the app would actually decide.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO

from atis_inference import find_model_path, get_conf_threshold
from evaluate_model import (
    CLASSES,
    IMAGE_EXTS,
    per_class_report,
    predict_probs,
    safety_at_threshold,
)


def gather_field_split(field_dir: Path) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    for cls in CLASSES:
        cls_dir = field_dir / cls
        if cls_dir.is_dir():
            for path in sorted(cls_dir.iterdir()):
                if path.suffix.lower() in IMAGE_EXTS:
                    items.append((path, cls))
    return items


def fmt_pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the ATIS classifier on field footage.")
    parser.add_argument(
        "--field-dir",
        required=True,
        help="Directory containing normal/ and cracked/ subfolders of site images.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Decision threshold to report at (default: production ATIS_CONF_THRESHOLD).",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Print the report but do not write it into model_card.json.",
    )
    args = parser.parse_args()

    field_dir = Path(args.field_dir).expanduser().resolve()
    items = gather_field_split(field_dir)
    if not items:
        raise SystemExit(
            f"No labelled images found under {field_dir}/normal and {field_dir}/cracked. "
            "See docs/field_validation_protocol.md."
        )

    model_path = find_model_path()
    if model_path is None:
        raise SystemExit("Model weights not found. Set ATIS_MODEL_PATH or provide best.pt.")

    threshold = args.threshold if args.threshold is not None else get_conf_threshold()

    print(f"Model:      {model_path}")
    print(f"Field data: {field_dir} ({len(items)} images)")
    print(f"Threshold:  {threshold:.2f}\n")

    model = YOLO(str(model_path))
    rows = predict_probs(model, items)
    report = per_class_report(rows)
    safety = safety_at_threshold(rows, threshold)

    print(f"=== FIELD per-class metrics (argmax) — accuracy {fmt_pct(report['accuracy'])} ===")
    print(f"{'class':<9}{'precision':>11}{'recall':>9}{'f1':>8}{'support':>9}")
    for cls in CLASSES:
        metrics = report["per_class"][cls]
        print(
            f"{cls:<9}{fmt_pct(metrics['precision']):>11}{fmt_pct(metrics['recall']):>9}"
            f"{fmt_pct(metrics['f1']):>8}{metrics['support']:>9}"
        )

    print(
        f"\nSAFETY @ {threshold:.2f}: "
        f"cracked recall {fmt_pct(safety['cracked_recall'])} "
        f"(missed-defect rate {fmt_pct(1 - safety['cracked_recall'])}) | "
        f"good tyres flagged {fmt_pct(safety['normal_false_flag'])}"
    )

    field_metrics = {
        "status": "recorded",
        "evaluated_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "field_dir": str(field_dir),
        "image_count": len(items),
        "support": {cls: report["per_class"][cls]["support"] for cls in CLASSES},
        "threshold": threshold,
        "accuracy": report["accuracy"],
        "per_class": report["per_class"],
        "safety_at_threshold": safety,
        "note": (
            "Field metrics from real checkpoint footage. These, not the curated "
            "test_metrics, gate whether verdicts may be enforced. See "
            "docs/field_validation_protocol.md and docs/model_governance.md."
        ),
    }

    if args.no_merge:
        print("\n(--no-merge set; model_card.json not updated)")
        print(json.dumps(field_metrics, indent=2))
        return

    card_path = model_path.parent.parent / "model_card.json"
    if card_path.exists():
        card = json.loads(card_path.read_text())
        card["field_metrics"] = field_metrics
        card_path.write_text(json.dumps(card, indent=2))
        print(f"\nMerged field metrics into {card_path}")
    else:
        print("\n(model_card.json not found; skipped metric merge)")
        print(json.dumps(field_metrics, indent=2))


if __name__ == "__main__":
    main()
