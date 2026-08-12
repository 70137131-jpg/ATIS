---
title: ATIS Tyre Inspection
emoji: 🛞
colorFrom: green
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
---

<!-- The YAML block above is Hugging Face Space metadata (Docker SDK): ignored on
     GitHub, required by HF Spaces to build and route the container on port 8080. -->

# Drive IQ / ATIS

Automated Tire Inspection System (ATIS) combines the trained YOLO tyre
classifier with the NHA operator dashboard in one Flask application.

Live application: https://atis-fyp.me/login

## What’s Included

- A YOLO classification dataset for `cracked` and `normal` tyre images.
- Training, evaluation, and single-image CLI scripts.
- A Flask dashboard with login, inspection uploads, history, alerts, reports,
  PDF export, and database models.
- A pure Python/OpenCV live camera workflow for fixed toll-booth tyre scan zones.
- Local SQLite demo data for immediate use, with optional PostgreSQL support
  for production or demo deployments.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The app defaults to SQLite at `instance/atis.db`. For a fresh checkout, apply
the schema and seed the demo users:

```bash
python3 -m flask --app app db upgrade
python3 -m flask --app app seed-demo-users
```

If you want the larger local sample history instead, use:

```bash
python3 seed.py
```

Copy `.env.example` to `.env` only if you need to override values such as
`DATABASE_URL`, `SECRET_KEY`, `ATIS_MODEL_PATH`, `YOLO_DEVICE`, or image
storage settings.

## Run The Dashboard

Start the Flask app locally:

```bash
python3 app.py
```

Open the dashboard at:

```text
http://127.0.0.1:5000
```

Demo accounts:

| Role | Email | Password |
| --- | --- | --- |
| Admin | admin@nha.gov.pk | admin123 |
| Operator | operator@nha.gov.pk | operator123 |
| Supervisor | supervisor@nha.gov.pk | super123 |
| Inspector | inspector@nha.gov.pk | inspect123 |

Demo passwords are stored hashed with Werkzeug. The table above lists the
plaintext values only so you can sign in to the local demo.

The `/predict` route uploads an image, auto-reads the licence plate when the
plate field is blank, runs the trained classifier from
`runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`, stores an
inspection row, and creates an alert when the prediction is unsafe.

## Production Setup

Configuration is controlled in `config.py` through environment variables. For a
production deployment, set `ATIS_ENV=production`. In that mode the app refuses
to start without a strong `SECRET_KEY`, disables demo seeding and demo login
aliases, and enables secure session cookies.

```bash
export ATIS_ENV=production
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/atis_db

# Optional production image storage:
# export ATIS_IMAGE_STORAGE=s3
# export ATIS_S3_BUCKET=atis-inspection-images
# export ATIS_S3_SIGNED_URLS=1

python3 -m flask --app app db upgrade
python3 -m flask --app app create-admin
gunicorn app:app
```

Security features active in every environment include hashed passwords, CSRF
protection on all form posts, login rate limiting, upload size limits plus image
content validation, HTTPOnly/SameSite session cookies, and `debug` off unless
`FLASK_DEBUG=1`.

By default, inspection images are stored in the database as blobs for demo use.
For production volume, set `ATIS_IMAGE_STORAGE=s3` and configure an
S3-compatible bucket so the database stores object keys and metadata instead of
image bytes.

## CLI Model Commands

Prepare the dataset:

```bash
python3 prepare_dataset.py
```

Train the classifier:

```bash
python3 train_model.py
```

Set a device explicitly only when needed:

```bash
YOLO_DEVICE=0 python3 train_model.py
YOLO_DEVICE=cpu python3 train_model.py
```

Evaluate the model:

```bash
python3 evaluate_model.py
```

Run single-image inference:

```bash
python3 test_tyre.py
```

## Live Camera Inspection

The live workflow is Python-only and uses OpenCV windows rather than a browser
camera. It assumes a fixed toll-booth camera position and calibrated tyre scan
zones.

Calibrate zones:

```bash
python3 calibrate_live_zones.py --camera 0
```

In the calibration window:

- Drag one or more tyre scan zones.
- Press `s` to save to `config/live_zones.json`.
- Press `c` to clear zones.
- Press `q` to quit without saving.

Run live inspection:

```bash
python3 live_video_inspection.py --camera 0
```

The dashboard also includes a browser-camera live area at:

```text
http://127.0.0.1:5000/live
```

That page uses the operator device camera through the browser `getUserMedia`
API, posts sampled frames to `/api/live/analyze`, and can log a selected frame
through the normal `/predict` upload route. The standalone
`live_video_inspection.py` script remains available for server-side OpenCV
camera tests with calibrated fixed zones.

Runtime keys:

- `q` quits.
- `p` pauses or resumes analysis.
- `r` resets live streak counters.

Live dashboard defaults:

- Frames are analyzed roughly once per second while the camera is active.
- Live analysis is read-only; use “Capture & Log” to persist an inspection.
- Logged frames appear in dashboard history and alerts through the normal inspection flow.
- Configure live API limits with `ATIS_LIVE_FRAME_MAX_MB` and `ATIS_LIVE_FRAME_MAX_PIXELS`.

## Model Notes

ATIS currently runs a YOLOv11 classifier trained for `normal` versus `cracked`.
The committed model card is at
`runs/classify/runs/classify/ATIS_Project/tyre_safety_model/model_card.json`.

Classifier output is mapped to the dashboard as follows:

- `normal` with confidence above `ATIS_CONF_THRESHOLD` becomes `safe`.
- `cracked` / `crack` / `cracking` becomes `unsafe` with defect `Cracking`.
- Low-confidence `normal` becomes `unsafe` and is flagged for manual review.

When a tyre is classified as cracked, `atis_inference.py` uses a lightweight
OpenCV crack localizer to draw marker boxes over likely crack regions. Those
boxes are heuristic visual aids, not trained detector bounding boxes.

`train_detector.py` is present for a future YOLO detection model, but the web
app does not currently load detector weights or claim multi-defect detection.

Held-out test metrics recorded on 2026-07-04 via `evaluate_model.py` on the
298-image test split are documented in `model_card.json` under `test_metrics`.
These are curated-dataset numbers and do not yet prove performance on live
checkpoint cameras.

Threshold calibration and the classifier-versus-detector decision are described
in `docs/model_threshold_calibration.md`.

Dataset and model storage rules are documented in `docs/artifact_policy.md`.
Keep runtime weights that the app loads in Git LFS, and keep datasets, dataset
archives, scratch checkpoints, and generated training runs outside Git.

> Limitation: the current model only distinguishes normal versus cracked tyres
> in a single static image. Conditions such as under- or over-inflation are out
> of scope.

## PostgreSQL Option

SQLite is the local default. To use PostgreSQL instead:

```bash
cp .env.example .env
# Edit DATABASE_URL in .env
python3 -m flask --app app db upgrade
python3 migrate_sqlite_to_postgres.py
```

Use `python3 migrate_sqlite_to_postgres.py --replace` only when intentionally
replacing existing PostgreSQL rows.

## Project Layout

```text
app.py                  Flask app factory, auth guard, CLI commands, health endpoints
config.py               Centralised configuration and production validation
security.py             Security headers (CSP, HSTS, nosniff, Referrer-Policy)
observability.py        Structured logging and Sentry hooks
metrics.py              Prometheus-style /metrics exposition
models.py               SQLAlchemy models
atis_inference.py       Shared YOLO classifier inference helper
routes/                 Flask blueprints (auth, inspections, live, alerts,
                        reports, users, operations, audit; common.py holds
                        shared decorators and role groups)
services/               Business logic (inference jobs, reports, ANPR, audit,
                        image storage, retention, MFA/TOTP, login security,
                        model monitoring and feedback export)
templates/              Jinja2 pages
static/                 CSS, JS (incl. self-hosted vendor JS), fonts, images
migrations/             Flask-Migrate / Alembic migrations
tests/                  Pytest suite
docs/                   Governance, security/ops, and model documentation
scripts/                Database backup and restore helpers
config/                 Live zone examples and runtime config
instance/               Local SQLite database (gitignored)

prepare_dataset.py      Build the Ultralytics dataset layout from image sources
train_model.py          Train YOLO classifier
train_detector.py       Scaffold for a future detector (not wired into the app)
evaluate_model.py       Validate trained classifier + threshold sweep
field_validation.py     Evaluate on real checkpoint footage (model governance G3)
test_tyre.py            CLI single-image classifier test
calibrate_live_zones.py Draw fixed live camera tyre scan zones
live_video_inspection.py OpenCV live camera inspection runner
ATIS_Dataset/           Ultralytics classification dataset (gitignored)
runs/classify/...       Trained ATIS classifier weights (Git LFS)
```
