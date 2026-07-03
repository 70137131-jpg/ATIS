# Model Feedback Export

ATIS stores human review decisions on inspections. Reviewed inspections with a
`correction_label` can be exported as a retraining dataset from:

```text
/api/model-feedback/export?from=YYYY-MM-DD&to=YYYY-MM-DD
```

The Reports page exposes the same export as **Export Feedback ZIP**.

## Archive Layout

The ZIP contains:

- `manifest.csv` — traceability metadata for each image
- `images/<label>/inspection_<id>.<ext>` — corrected images grouped by label
- `README.txt` — brief archive notes

Only inspections with all of the following are included:

- a human review correction label
- an available stored image
- an inspection timestamp inside the selected date range

Rows with a correction label but missing image bytes are skipped and counted in
the `model_feedback.exported` audit event.

## Training Use

For the current classifier path, use the `images/<label>/...` folders as a
reviewed source dataset. Before training:

1. Inspect `manifest.csv` for label balance and obvious review mistakes.
2. Merge the corrected images into a new train/val/test split.
3. Keep the original `inspection_id`, `model_version`, and `review_status`
   columns in experiment notes for traceability.
4. Run evaluation before replacing the production `best.pt` artifact.

Do not overwrite the existing training dataset directly. Treat each feedback
export as an auditable input to a new dataset version.
