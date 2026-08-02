# ATIS Model Governance

This defines who is accountable for the model's verdicts, the gates a model must
clear before its verdicts may be *enforced* (versus advisory), and how the live
model is monitored. It complements the technical calibration in
`docs/model_threshold_calibration.md` and the honest `model_card.json`.

## 1. Accountability

| Question | Owner |
|----------|-------|
| Is the model fit to enforce verdicts? | **Model owner: [name/role]** — signs the go/no-go gate below. |
| Who is liable for a false negative (cracked tyre passed)? | **[NHA system owner]** — documented, not implicit. |
| Who monitors live performance and responds to drift? | **[operations owner]** — runs/reviews `atis-model-monitor`. |
| Who approves a model change / retrain to production? | **[model owner + system owner]**. |

A **false negative is the safety-critical failure**: a cracked tyre labelled
safe on a public highway. Every gate and monitor below is weighted toward
catching that, at the cost of some false flags (which review handles).

## 2. Verdict enforcement status

State explicitly, per deployment, which mode ATIS is in:

- **Advisory (default):** verdicts assist an operator; no action is taken on the
  model's output alone. Appropriate until Gate 3 is signed.
- **Enforcing:** the verdict triggers a real consequence. **Not permitted until
  all gates below are signed off.**

## 3. Go / no-go gates

| Gate | Requirement | Evidence | Status |
|------|-------------|----------|--------|
| **G1 — Curated evaluation** | Held-out test metrics recorded, cracked-recall target met | `model_card.json → test_metrics` | ✅ recorded 2026-07-04 |
| **G2 — Model↔app contract** | The real weights run through the app and return a valid contract | `tests/test_model_contract.py` | ✅ automated |
| **G3 — Field validation** | Metrics on **real checkpoint footage** across conditions meet the safety bar | `model_card.json → field_metrics` via `field_validation.py` | ⛔ **required before enforcing** |
| **G4 — Live monitoring** | Drift/missed-defect monitoring scheduled and alerting | `atis-model-monitor --strict` in cron | ⛔ configure at deploy |
| **G5 — Sign-off** | Model owner + system owner approve enforcement | this document | ⛔ pending |

Do not promise capabilities the model does not have (per
`model_card.json → known_limitations`): it is a binary `normal`/`cracked`
classifier; the overlay boxes are heuristic, not trained detections; there is no
bulge/puncture/tread/inflation detection and no validated night performance.

## 4. Field validation (Gate 3)

Curated metrics use studio/web imagery and **do not** prove field performance.
Collect real footage per `docs/field_validation_protocol.md`, then:

```bash
python3 field_validation.py --field-dir /path/to/field_dataset
```

This records `field_metrics` in the model card at the production decision
threshold. **Acceptance bar (set with the system owner), e.g.:**

- cracked recall (field) **≥ [0.95]** → missed-defect rate ≤ [5%]
- false-flag rate **≤ [operationally acceptable %]**
- validated across: day/night, wet/dirty, motion blur, glare, partial-frame,
  and deliberate non-tyre inputs.

## 5. Live monitoring (Gate 4)

`atis-model-monitor` derives operational signals from stored inspections — no
extra logging needed:

```bash
# Human-readable snapshot
flask --app app atis-model-monitor --window-days 7

# Cron: page when the live missed-defect rate breaches the safety threshold
0 6 * * * cd /app && flask --app app atis-model-monitor --strict || /usr/local/bin/page-oncall
```

Key signal: **live missed-defect rate** — reviewers relabelling a *passed* tyre
as cracked. Watch also the confidence distribution and the not-tyre / unsafe
rates for drift (a shifting input distribution precedes accuracy loss). The
review corrections feed the retraining export
(`services/model_feedback.py`, `docs/model_feedback_export.md`).

## 6. Model change control

A retrain or threshold change reaching production must:
1. Re-run `evaluate_model.py` (G1) and commit the updated `model_card.json`.
2. Pass `tests/test_model_contract.py` (G2).
3. Re-run `field_validation.py` (G3) if the input distribution or model changed
   materially.
4. Record the new weights' SHA-256 (already pinned in the Dockerfile and card).
5. Be signed off (G5).
