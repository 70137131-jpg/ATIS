"""
train_model.py — Train the ATIS YOLOv11 tire-safety classifier.

Reproducible, safety-oriented training config:
  - early stopping (patience) + cosine LR schedule
  - rotation augmentation (tires appear at varied angles at a checkpoint)
  - fixed seed + deterministic mode
Run prepare_dataset.py first so ATIS_Dataset/{train,val,test} exists.

After training it writes a model_card.json next to the weights recording the
dataset counts, hyperparameters, base model, git SHA and date for provenance.
evaluate_model.py later merges the test-set metrics + tuned threshold into it.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "ATIS_Dataset"
BASE_MODEL = "yolo11n-cls.pt"
PROJECT = "ATIS_Project"          # lands at runs/classify/ATIS_Project/tyre_safety_model
RUN_NAME = "tyre_safety_model"

TRAIN_ARGS = {
    "data": str(DATASET_DIR),
    "epochs": 100,           # generous; early stopping ends it sooner
    "patience": 20,          # stop if val hasn't improved for 20 epochs
    "imgsz": 224,
    "batch": 32,
    "seed": 0,
    "deterministic": True,
    "cos_lr": True,          # cosine LR decay
    "degrees": 20.0,         # NEW: rotation augmentation (was 0)
    "fliplr": 0.5,
    "project": PROJECT,
    "name": RUN_NAME,
    "exist_ok": True,
}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR, text=True
        ).strip()
    except Exception:
        return "unknown"


def dataset_counts() -> dict:
    counts: dict[str, dict[str, int]] = {}
    for split in ("train", "val", "test"):
        split_dir = DATASET_DIR / split
        if not split_dir.is_dir():
            continue
        counts[split] = {
            cls.name: sum(1 for _ in cls.iterdir())
            for cls in sorted(split_dir.iterdir())
            if cls.is_dir()
        }
    return counts


def write_model_card(save_dir: Path) -> None:
    card = {
        "model": "ATIS tire-safety classifier",
        "base_model": BASE_MODEL,
        "task": "classification (normal vs cracked)",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "hyperparameters": {k: v for k, v in TRAIN_ARGS.items() if k != "data"},
        "dataset_counts": dataset_counts(),
        "weights": str((save_dir / "weights" / "best.pt").relative_to(BASE_DIR)),
        "test_metrics": "run evaluate_model.py to populate",
    }
    card_path = save_dir / "model_card.json"
    card_path.write_text(json.dumps(card, indent=2))
    print(f"Wrote model card: {card_path.relative_to(BASE_DIR)}")


def train_atis_classifier() -> None:
    if not (DATASET_DIR / "train").is_dir():
        raise SystemExit(
            f"{DATASET_DIR}/train not found. Run: python3 prepare_dataset.py [--source ...]"
        )

    model = YOLO(BASE_MODEL)

    args = dict(TRAIN_ARGS)
    device = os.environ.get("YOLO_DEVICE")
    if device:
        args["device"] = device

    print("Starting YOLOv11 classification training...")
    print(f"  dataset counts: {dataset_counts()}")
    results = model.train(**args)

    save_dir = Path(results.save_dir)
    write_model_card(save_dir)
    print(f"Training complete. Weights under {save_dir / 'weights'}")


if __name__ == "__main__":
    train_atis_classifier()
