# ATIS Model Threshold Calibration

## Current Product Decision

ATIS should continue to run the trained YOLOv11 image classifier plus the OpenCV
crack-localizer heuristic for the current product path.

The committed trained artifact is a `normal` vs `cracked` classifier:

- `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`
- model card: `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/model_card.json`

The app should not fully switch to the detector path yet. `train_detector.py`
is a scaffold for a future YOLO detection model, but the repo does not currently
contain trained detector weights, detector test metrics, or per-defect mAP
evidence. The OpenCV boxes in the UI are visual aids for cracked-class outputs,
not trained detector boxes.

Switch to a trained detector only after all of these are true:

- A detection dataset with clean negatives and labelled tyre-defect boxes is
  available through the repo or documented external artifact storage.
- Detector weights are available through the agreed model artifact policy.
- Evaluation reports per-class precision, recall, mAP, and product-level
  false-pass / false-flag rates.
- `atis_inference.py` and tests parse detector result objects directly.

## Threshold Policy

`ATIS_CONF_THRESHOLD` is the minimum top-1 probability for a `normal` prediction
to pass as `safe`. The default is `0.60`.

The policy is intentionally asymmetric:

- `normal` with confidence >= threshold -> `safe`
- `normal` with confidence < threshold -> `unsafe`, manual review
- `cracked`, `crack`, or `cracking` -> `unsafe` regardless of confidence
- unknown classifier class -> `unsafe`, manual review

This avoids waving through low-confidence normal predictions.

## Current Calibration Status

The training run reached high validation accuracy in `results.csv`:

- epoch 95 best top-1 validation accuracy: `0.99197`
- epoch 92 best validation loss: `0.03143`
- epoch 100 final top-1 validation accuracy: `0.98555`

Those are training validation artifacts, not a substitute for held-out product
calibration. The current repo does not include a fresh `evaluate_model.py` output
merged into the model card, so keep the production threshold at `0.60` until the
held-out test split is restored and evaluated.

## Calibration Runbook

1. Restore `ATIS_Dataset/{train,val,test}/{normal,cracked}` with the exact split
   described in `DATA_HANDOFF.md`, or rebuild a newer split and record its counts.
2. Run:

   ```bash
   python3 evaluate_model.py
   ```

3. Confirm the script prints:

   - argmax per-class precision, recall, F1, and confusion matrix on test
   - threshold selected on validation split
   - cracked recall and normal recall on test at the selected threshold

4. Accept a threshold only if the cracked recall target is met on validation and
   the held-out test false-flag rate is acceptable for the operating workflow.
5. Update `ATIS_CONF_THRESHOLD` in deployment configuration and commit the updated
   model card with the merged `test_metrics` section.

## Product Reporting Rules

Allowed claims:

- binary tyre image classification: `normal` vs `cracked`
- fail-safe manual review for low-confidence normal predictions
- heuristic crack-region visual marker boxes

Do not claim yet:

- trained defect detection
- per-defect localization accuracy
- bulge, puncture, tread, inflation, or flat-spot detection
- night/low-light reliability without controlled lighting or new evaluation data
