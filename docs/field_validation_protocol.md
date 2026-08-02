# ATIS Field Validation Protocol

The metrics in `model_card.json → test_metrics` come from curated studio/web
images. They are necessary but **not sufficient**: they do not prove the model
works on the target checkpoint cameras. This protocol describes how to collect a
representative field dataset and produce honest field metrics that gate whether
verdicts may be enforced (Gate 3 in `docs/model_governance.md`).

## 1. What to collect

Photograph tyres **at the deployment site, through the deployment camera(s)**,
and confirm each one's true label by physical inspection. Aim for balanced,
condition-diverse coverage. Minimum suggested counts per condition (tune with the
model owner):

| Condition | Why it matters | Min images (normal / cracked) |
|-----------|----------------|-------------------------------|
| Daylight, clean, dry | Baseline | 50 / 50 |
| Night / checkpoint lighting | Model untrained for low light | 50 / 50 |
| Wet tyre | Water changes texture/reflectance | 30 / 30 |
| Dirty / muddy | Occludes cracks | 30 / 30 |
| Motion blur (vehicle moving) | Real capture condition | 30 / 30 |
| Glare / harsh shadow | Sensor/lighting artefacts | 20 / 20 |
| Partial tyre in frame | Framing reality | 20 / 20 |
| **Non-tyre inputs** (road, bumper, person, empty frame) | Tests the non-tyre gate | 50 (label separately, see §4) |

Balance matters more than raw volume: a few hundred well-labelled, diverse
images beats thousands of easy daylight shots.

## 2. Labelling

Ground truth must come from **physical inspection**, not from the model. Two
reviewers should agree on `cracked` vs `normal`; resolve disagreements by
inspection. Record who labelled each batch and when.

## 3. Directory layout

```
field_dataset/
    normal/    *.jpg   # confirmed-good tyres, all conditions mixed
    cracked/   *.jpg   # confirmed-cracked tyres, all conditions mixed
```

Keep the raw images **out of Git** (they are personal data and large) — store
them in the agreed artifact/object storage, per `docs/artifact_policy.md`.

## 4. Non-tyre inputs

The classifier is binary; non-tyre frames test the *gate*
(`atis_inference._non_tyre_reason`), not the classifier. Evaluate those
separately: feed them through `/predict` (or `classify_tyre_image`) and confirm
they come back `predicted_class == "not_tyre"`. Record the pass rate; a low rate
means the gate needs tuning (`ATIS_FLAT_*`, `ATIS_OBJECT_CONF_THRESHOLD`) or the
object model.

## 5. Run the evaluation

```bash
python3 field_validation.py --field-dir /path/to/field_dataset
```

This reuses the exact honest, safety-focused scoring in `evaluate_model.py`,
reports per-class precision/recall/F1 and the safety numbers at the **production
threshold** (`ATIS_CONF_THRESHOLD`), and writes them into
`model_card.json → field_metrics` (distinct from the curated `test_metrics`).

## 6. Acceptance

Compare against the bar agreed in `docs/model_governance.md §4`, e.g. cracked
recall ≥ 0.95 with an operationally acceptable false-flag rate, **and** adequacy
across every condition above (not just the aggregate). Until this is signed,
keep ATIS in **advisory** mode.

## 7. Re-validate when

- the camera, lens, mounting, or lighting changes;
- the model is retrained or the threshold changes materially;
- monitoring (`atis-model-monitor`) shows drift in the input distribution or a
  rising live missed-defect rate.
