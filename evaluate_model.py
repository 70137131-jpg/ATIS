"""
evaluate_model.py — Honest, safety-focused evaluation of the ATIS classifier.

Reports, on the held-out **test** split:
  - per-class precision / recall / F1 and a confusion matrix (argmax)
  - the two safety numbers: cracked recall (1 - missed-defect rate) and
    normal recall (1 - false-flag rate)

Then runs a **threshold sweep on the val split** to pick the smallest "min P(normal)
to pass as safe" cutoff that catches at least TARGET_CRACKED_RECALL of cracked tires,
and reports the resulting test-set safety metrics at that operating point. The chosen
value is what you set as ATIS_CONF_THRESHOLD in production.

Results are merged into the model's model_card.json.
"""

import json
from collections import defaultdict
from pathlib import Path

from ultralytics import YOLO

from atis_inference import find_model_path

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "ATIS_Dataset"
CLASSES = ("normal", "cracked")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TARGET_CRACKED_RECALL = 0.95


def gather_split(split: str) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    for cls in CLASSES:
        cls_dir = DATASET_DIR / split / cls
        if cls_dir.is_dir():
            for p in sorted(cls_dir.iterdir()):
                if p.suffix.lower() in IMAGE_EXTS:
                    items.append((p, cls))
    return items


def predict_probs(model, items: list[tuple[Path, str]]) -> list[tuple[str, str, float]]:
    """Return [(true_class, pred_class, p_normal)] for each image."""
    out: list[tuple[str, str, float]] = []
    paths = [str(p) for p, _ in items]
    results = model.predict(paths, verbose=False)
    for (_, true_cls), res in zip(items, results):
        names = res.names  # {idx: name}
        probs = res.probs.data.tolist()
        name_to_p = {names[i].lower(): probs[i] for i in range(len(probs))}
        p_normal = name_to_p.get("normal", 0.0)
        pred_cls = names[int(res.probs.top1)].lower()
        out.append((true_cls, pred_cls, p_normal))
    return out


def per_class_report(rows: list[tuple[str, str, float]]) -> dict:
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    confusion = {t: defaultdict(int) for t in CLASSES}  # true -> pred -> count

    for true_cls, pred_cls, _ in rows:
        confusion[true_cls][pred_cls] += 1
        if pred_cls == true_cls:
            tp[true_cls] += 1
        else:
            fp[pred_cls] += 1
            fn[true_cls] += 1

    report = {}
    for c in CLASSES:
        precision = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        recall = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        report[c] = {"precision": precision, "recall": recall, "f1": f1,
                     "support": tp[c] + fn[c]}
    accuracy = sum(tp.values()) / len(rows) if rows else 0.0
    return {"per_class": report, "accuracy": accuracy, "confusion": confusion}


def safety_at_threshold(rows: list[tuple[str, str, float]], threshold: float) -> dict:
    """Decision: safe iff p_normal >= threshold, else unsafe. Returns safety rates."""
    cracked_total = sum(1 for t, _, _ in rows if t == "cracked")
    normal_total = sum(1 for t, _, _ in rows if t == "normal")
    cracked_caught = sum(1 for t, _, pn in rows if t == "cracked" and pn < threshold)
    normal_passed = sum(1 for t, _, pn in rows if t == "normal" and pn >= threshold)
    return {
        "threshold": threshold,
        "cracked_recall": cracked_caught / cracked_total if cracked_total else 0.0,
        "normal_recall": normal_passed / normal_total if normal_total else 0.0,
        "normal_false_flag": 1 - (normal_passed / normal_total) if normal_total else 0.0,
    }


def choose_threshold(val_rows: list[tuple[str, str, float]]) -> dict:
    """Smallest min-P(normal) cutoff hitting TARGET_CRACKED_RECALL on val."""
    sweep = [safety_at_threshold(val_rows, t / 100) for t in range(50, 100)]
    qualifying = [s for s in sweep if s["cracked_recall"] >= TARGET_CRACKED_RECALL]
    chosen = min(qualifying, key=lambda s: s["threshold"]) if qualifying else max(
        sweep, key=lambda s: s["cracked_recall"]
    )
    return {"chosen": chosen, "sweep": sweep, "target": TARGET_CRACKED_RECALL,
            "target_met": bool(qualifying)}


def fmt_pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def main() -> None:
    model_path = find_model_path()
    if model_path is None:
        raise SystemExit("Model weights not found. Train the classifier first or set ATIS_MODEL_PATH.")
    if not (DATASET_DIR / "test").is_dir():
        raise SystemExit("ATIS_Dataset/test not found. Run prepare_dataset.py first.")

    print(f"Evaluating: {model_path}")
    model = YOLO(str(model_path))

    test_rows = predict_probs(model, gather_split("test"))
    val_rows = predict_probs(model, gather_split("val"))

    # --- Per-class report (argmax) on test ---
    rep = per_class_report(test_rows)
    print(f"\n=== TEST per-class metrics (argmax) — accuracy {fmt_pct(rep['accuracy'])} ===")
    print(f"{'class':<9}{'precision':>11}{'recall':>9}{'f1':>8}{'support':>9}")
    for c in CLASSES:
        m = rep["per_class"][c]
        print(f"{c:<9}{fmt_pct(m['precision']):>11}{fmt_pct(m['recall']):>9}"
              f"{fmt_pct(m['f1']):>8}{m['support']:>9}")

    print("\nConfusion matrix (rows = true, cols = predicted):")
    print(f"{'true\\pred':<10}" + "".join(f"{c:>9}" for c in CLASSES))
    for t in CLASSES:
        print(f"{t:<10}" + "".join(f"{rep['confusion'][t][p]:>9}" for p in CLASSES))

    print(f"\nSAFETY (argmax): missed-defect rate = {fmt_pct(1 - rep['per_class']['cracked']['recall'])}"
          f" | good tires flagged = {fmt_pct(1 - rep['per_class']['normal']['recall'])}")

    # --- Threshold sweep (tuned on val), reported on test ---
    sel = choose_threshold(val_rows)
    chosen_t = sel["chosen"]["threshold"]
    test_at = safety_at_threshold(test_rows, chosen_t)
    print(f"\n=== Threshold sweep (target cracked recall >= {fmt_pct(sel['target'])}, tuned on VAL) ===")
    if not sel["target_met"]:
        print("  WARNING: target not reachable; using the most defect-catching threshold available.")
    print(f"  Chosen ATIS_CONF_THRESHOLD = {chosen_t:.2f}")
    print(f"  On VAL : cracked recall {fmt_pct(sel['chosen']['cracked_recall'])}"
          f" | normal recall {fmt_pct(sel['chosen']['normal_recall'])}")
    print(f"  On TEST: cracked recall {fmt_pct(test_at['cracked_recall'])}"
          f" | normal recall {fmt_pct(test_at['normal_recall'])}"
          f" | good tires flagged {fmt_pct(test_at['normal_false_flag'])}")

    # --- Merge into model card ---
    card_path = model_path.parent.parent / "model_card.json"
    if card_path.exists():
        card = json.loads(card_path.read_text())
        card["test_metrics"] = {
            "accuracy": rep["accuracy"],
            "per_class": rep["per_class"],
            "safety_argmax": {
                "missed_defect_rate": 1 - rep["per_class"]["cracked"]["recall"],
                "good_flagged_rate": 1 - rep["per_class"]["normal"]["recall"],
            },
            "chosen_threshold": chosen_t,
            "test_at_threshold": test_at,
        }
        card_path.write_text(json.dumps(card, indent=2))
        print(f"\nMerged metrics into {card_path.name}")
    else:
        print("\n(model_card.json not found; skipped metric merge)")


if __name__ == "__main__":
    main()
