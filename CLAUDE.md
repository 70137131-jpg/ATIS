# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ATIS (Automated Tire Inspection System) couples a YOLOv11 nano **classifier**
(not a detector — it returns image-level class probabilities, no bounding boxes)
with a Flask operator dashboard for Pakistan's NHA. The classifier labels a tire
image as `normal` or `cracked`; the dashboard records each inspection, raises
alerts on unsafe results, and produces charts and PDF reports.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run the dashboard (debug server on http://127.0.0.1:5000)
python3 app.py

# ML pipeline
python3 prepare_dataset.py      # "Tire Textures/" -> "ATIS_Dataset/" (Ultralytics layout)
python3 train_model.py          # trains 50 epochs, writes weights under ATIS_Project/
python3 evaluate_model.py       # top-1 accuracy on ATIS_Dataset/val
python3 test_tyre.py            # single-image CLI inference (edit SAMPLE_IMAGE in the file)

# Force a device for training/inference (default: auto)
YOLO_DEVICE=0 python3 train_model.py     # also accepts: cpu, mps

# Database seeding
python3 seed.py                 # DROPS all tables, recreates, loads rich demo data

# PostgreSQL (SQLite is the default; no setup needed for local dev)
cp .env.example .env            # set DATABASE_URL=postgresql+psycopg2://...
python3 -m flask --app app db upgrade
python3 migrate_sqlite_to_postgres.py            # copy SQLite rows into Postgres
python3 migrate_sqlite_to_postgres.py --replace  # only to overwrite existing Postgres rows

# Tests
python3 -m pytest

# Docker smoke build
docker build -t atis .
```

`test_tyre.py` is a CLI demo script, not a pytest test module.

## Architecture

**Inference is centralized in [atis_inference.py](atis_inference.py).** Both the
web app and CLI scripts call `classify_tyre_image()`. The YOLO model is
**lazy-loaded and cached** in module globals (`_classifier_model`), so it loads
once per process on first prediction. Model weights are resolved by
`find_model_path()`, which checks `ATIS_MODEL_PATH` first, then several relative
candidates. The class→status mapping lives in `_status_for_class()` and is
gated by an **asymmetric, fail-safe confidence threshold** (`get_conf_threshold()`,
env `ATIS_CONF_THRESHOLD`, default `0.60`): a tire is passed as `safe` **only**
when predicted `normal` *and* top-1 confidence ≥ threshold. A `cracked`
prediction is `unsafe` at any confidence; a low-confidence `normal` is downgraded
to `unsafe` with the defect "Low-confidence normal — manual review"; **any
unexpected class is also `unsafe`**. The returned dict includes `threshold` and
a `low_confidence` flag for transparency. Note the model is a 2-class softmax, so
the winning confidence is always ≥ 0.50 — a threshold only bites above that.

**[app.py](app.py) owns the Flask app factory** (`create_app`) and extension
initialization. Routes are split under `routes/`, with shared decorators and
context helpers in `routes/common.py`. Key flows:
- `/predict` (file upload) and `/api/live/analyze` (browser camera frames) both
  funnel through `services.inspections.create_inspection_record()`, which writes
  an `Inspection`, records `created_by_id`, stores upload metadata/checksum, and
  **when status is `unsafe`, auto-creates a pending `Alert`** in the same
  transaction.
- The `/api/reports/*` endpoints live in `routes/reports.py`; aggregation helpers
  live in `services/reports.py`, and `/api/reports/export-pdf` builds a landscape
  PDF with reportlab while logging an audit event.
- `inject_nha_status()` is a `context_processor` that feeds pending-alert counts
  and recent alerts into every template, so the header badges work app-wide.

**Auth is session-based.** Passwords are **hashed** with Werkzeug
(`User.set_password()` / `User.check_password()` in [models.py](models.py)) —
never stored in plain text. `login()` verifies via `check_password()`. Every
protected route goes through the common auth decorators. User management is in
`routes/users.py`: admins can create users, change roles, enable/disable
accounts, and reset passwords. Users can change their own password at
`/account/password`.

**Security config is centralised in [config.py](config.py)** and loaded via
`app.config.from_object(Config)`. `Config.validate()` **fails fast in production**
(`ATIS_ENV=production`) if `SECRET_KEY` is missing/default. CSRF protection
(Flask-WTF) covers all form POSTs — every form template includes
`{{ csrf_token() }}`. Login is rate-limited (Flask-Limiter). Uploads are capped
(`MAX_CONTENT_LENGTH`) and content-verified with PIL in `/predict`. Session
cookies are HTTPOnly/SameSite=Lax (and Secure in production). `debug` is driven
by `FLASK_DEBUG` (default **off**), not hardcoded.

**[models.py](models.py)** defines `User`, `Inspection`, `Alert`, `AuditEvent`,
`DefectType`, and `InspectionDefect`. New prediction writes use structured
`InspectionDefect` rows for report/filter/model-feedback data. The legacy
`Inspection.defects` comma-separated string is retained as a backwards-compatible
cache; use the `defect_list` property in templates and reports.

**Database selection is automatic** ([config.py](config.py) `get_database_url`):
defaults to SQLite at `instance/atis.db`, switches to Postgres if `DATABASE_URL`
is set (and rewrites legacy `postgres://` → `postgresql://`). On startup,
`ensure_local_database()` creates tables and seeds demo users **only in
development** (gated on SQLite *and* `Config.SEED_DEMO_DATA`, which is false in
production). Provision the first production admin with
`flask --app app create-admin`. Postgres relies on the Alembic migrations in
`migrations/`.

## Conventions

- **Datetimes are naive-UTC by convention.** Columns are `db.DateTime` without
  `timezone=True`; defaults call `datetime.now(timezone.utc)` and both SQLite and
  Postgres `timestamp` store the value with the tzinfo dropped. Treat every stored
  datetime as UTC. Do NOT flip columns to `timezone=True` piecemeal — it changes
  SQLite string storage and Postgres comparisons at once, so it must be done as a
  single dedicated migration + code sweep.
- **Legacy string columns** (`Inspection.location`, `.camera`, `.defects`) are a
  write-through cache kept for old rows/reports; the structured versions
  (`location_id`, `camera_id`, `InspectionDefect`) are authoritative for new
  writes. Planned deprecation: stop reading the strings first, then drop columns
  in a later migration.

## Gotchas

- **Demo login aliases:** the README advertises `*@nha.gov.pk` accounts, but the
  seeded users are `*@atis.com`. `login()` maps the nha.gov.pk emails to the
  atis.com accounts. Both forms work; the stored email is the atis.com one.
- **Weights location vs. README:** `train_model.py` sets `project="ATIS_Project"`,
  so weights land in `ATIS_Project/tyre_safety_model/weights/best.pt`. The
  inference resolver also checks `runs/classify/...`, so both layouts work.
- **Artifact policy:** runtime model weights stay in Git LFS when the app needs
  them. Datasets, dataset zips, scratch checkpoints, and generated training runs
  stay outside the repo; see `docs/artifact_policy.md`.
- `instance/` (the SQLite DB) and `static/uploads/*` are gitignored; runtime data
  is not committed.
