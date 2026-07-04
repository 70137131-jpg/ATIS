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

**Held-out test evaluation recorded 2026-07-04** (`evaluate_model.py`, test split
152 cracked / 146 normal, threshold swept on the val split; merged into
`model_card.json` under `test_metrics`):

- test top-1 accuracy (argmax): `99.0%` (confusion: 1 cracked missed, 2 normal flagged)
- cracked recall: `99.3%` → missed-defect rate `0.7%`
- normal recall: `98.6%` → false-flag rate `1.4%`
- threshold sweep: the smallest cutoff meeting the `>= 95%` cracked-recall target
  on val is `0.50`; at that point test cracked recall is `99.3%` and false-flag
  rate `1.4%`.

The production default `ATIS_CONF_THRESHOLD=0.60` sits **above** the minimum
qualifying cutoff, so it is at least as defect-catching — keep `0.60`.

Context from training (`results.csv`): epoch 95 best top-1 validation accuracy
`0.99197`; epoch 100 final `0.98555`.

These are curated-dataset numbers (largely controlled/web imagery). They are
necessary but not sufficient for production: field validation on the target
checkpoint cameras (day/night, wet/dirty tyres, blur, glare, partial frames,
non-tyre inputs) is still required — see the go-live checklist in `DEPLOY.md`.

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
