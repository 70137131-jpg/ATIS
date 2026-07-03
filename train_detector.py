"""
train_detector.py — Train the ATIS YOLOv11 tyre-defect **detector**.

This replaces the old 2-class classifier (train_model.py) with an object-detection
model that localises each defect with a bounding box, so the dashboard can draw
real boxes and report the specific defect classes the dataset actually annotates.

Data comes from a YOLO **detection** dataset (e.g. a Roboflow "YOLOv11" export):

    datasets/tyre_defect/
      data.yaml          # names: [crack, bulge, ...], train:/val:/test: paths
      train/images  train/labels
      valid/images  valid/labels
      test/images   test/labels

Run on a GPU (Colab). Point --data / ATIS_DATA_YAML at your data.yaml.
After training it runs validation and writes a model_card.json (mAP, per-class
metrics, classes, git SHA, date) next to the weights for provenance/honest docs.

    python3 train_detector.py --data datasets/tyre_defect/data.yaml --epochs 100
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_YAML = BASE_DIR / "datasets" / "tyre_defect" / "data.yaml"
BASE_MODEL = "yolo11n.pt"          # detection base (NOT yolo11n-cls.pt)
PROJECT = "ATIS_Project"           # lands at runs/detect/ATIS_Project/tyre_defect_model
RUN_NAME = "tyre_defect_model"


def build_train_args(data_yaml: Path, epochs: int) -> dict:
    return {
        "data": str(data_yaml),
        "epochs": epochs,          # generous; early stopping ends it sooner
        "patience": 20,            # stop if val mAP hasn't improved for 20 epochs
        "imgsz": 640,              # detection needs more resolution than 224
        "batch": 16,
        "seed": 0,
        "deterministic": True,
        "cos_lr": True,            # cosine LR decay
        "degrees": 15.0,           # rotation aug (tyres appear at varied angles)
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


def read_classes(data_yaml: Path) -> list[str]:
    try:
        import yaml

        data = yaml.safe_load(data_yaml.read_text())
        names = data.get("names", [])
        if isinstance(names, dict):
            return [names[k] for k in sorted(names)]
        return list(names)
    except Exception:
        return []


def write_model_card(save_dir: Path, data_yaml: Path, train_args: dict, metrics: dict) -> None:
    card = {
        "model": "ATIS tyre-defect detector",
        "base_model": BASE_MODEL,
        "task": "object detection (per-defect bounding boxes)",
        "classes": read_classes(data_yaml),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "hyperparameters": {k: v for k, v in train_args.items() if k != "data"},
        "data_yaml": str(data_yaml),
        "val_metrics": metrics,
        "weights": str((save_dir / "weights" / "best.pt")),
    }
    card_path = save_dir / "model_card.json"
    card_path.write_text(json.dumps(card, indent=2))
    print(f"Wrote model card: {card_path}")


def _val_metrics(model: YOLO) -> dict:
    """Run validation and return the headline detection metrics for the card."""
    try:
        res = model.val()
        box = res.box
        metrics = {
            "mAP50": round(float(box.map50), 4),
            "mAP50_95": round(float(box.map), 4),
            "precision": round(float(box.mp), 4),
            "recall": round(float(box.mr), 4),
        }
        try:
            names = model.names
            metrics["per_class_mAP50"] = {
                str(names[i]): round(float(v), 4) for i, v in zip(box.ap_class_index, box.ap50)
            }
        except Exception:
            pass
        return metrics
    except Exception as exc:  # noqa: BLE001
        return {"error": f"validation failed: {exc}"}


def train_atis_detector(data_yaml: Path, epochs: int) -> None:
    if not data_yaml.is_file():
        raise SystemExit(
            f"data.yaml not found at {data_yaml}. Download a YOLO detection dataset "
            "(e.g. Roboflow export) and pass --data <path>/data.yaml."
        )

    model = YOLO(BASE_MODEL)
    args = build_train_args(data_yaml, epochs)
    device = os.environ.get("YOLO_DEVICE")
    if device:
        args["device"] = device

    print(f"Starting YOLOv11 detection training on {data_yaml} ...")
    print(f"  classes: {read_classes(data_yaml)}")
    results = model.train(**args)

    save_dir = Path(results.save_dir)
    metrics = _val_metrics(model)
    print(f"  validation metrics: {metrics}")
    write_model_card(save_dir, data_yaml, args, metrics)
    print(f"Training complete. Weights under {save_dir / 'weights'}")
    print("Copy best.pt into the repo and commit via Git LFS so the app can load it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the ATIS tyre-defect detector.")
    parser.add_argument(
        "--data",
        default=os.environ.get("ATIS_DATA_YAML", str(DEFAULT_DATA_YAML)),
        help="Path to the YOLO detection data.yaml.",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parsed = parser.parse_args()
    train_atis_detector(Path(parsed.data).expanduser(), parsed.epochs)
