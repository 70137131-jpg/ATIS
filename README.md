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

Automated Tire Inspection System (ATIS) now combines the trained YOLO tire
classifier with the NHA operator dashboard in one Flask application.

The repository contains:

- A YOLO classification dataset for `cracked` and `normal` tire images.
- Training, evaluation, and single-image CLI scripts.
- A Flask dashboard with login, inspection uploads, history, alerts, reports,
  PDF export, and database models.
- A pure Python/OpenCV live camera workflow for fixed toll-booth tire scan zones.
- Local SQLite demo data for immediate use, with optional PostgreSQL migration
  support for production/demo deployments.

## Project Layout

```text
.
+-- app.py                         # Flask dashboard and API routes
+-- atis_inference.py              # Shared YOLO classifier inference helper
+-- models.py                      # SQLAlchemy models
+-- prepare_dataset.py             # Reformat Tire Textures into Ultralytics layout
+-- train_model.py                 # Train YOLO classifier
+-- evaluate_model.py              # Validate trained classifier
+-- test_tyre.py                   # CLI single-image classifier test
+-- calibrate_live_zones.py        # Draw fixed live camera tire scan zones
+-- live_video_inspection.py       # OpenCV live camera inspection runner
+-- config/live_zones.example.json # Example normalized zone config
+-- requirements.txt               # Dashboard + ML dependencies
+-- templates/                     # Jinja2 pages
+-- static/                        # CSS, JS, images, runtime uploads
+-- instance/atis.db               # Local SQLite demo database
+-- migrations/                    # Flask-Migrate/Alembic migrations
+-- Tire Textures/                 # Original image split
+-- ATIS_Dataset/                  # Ultralytics classification dataset
+-- runs/classify/.../best.pt      # Trained ATIS classifier weights
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The app defaults to SQLite at `instance/atis.db`. Initialize a fresh checkout
explicitly; the web process does not create or stamp schema on import:

```bash
python3 -m flask --app app db upgrade
python3 -m flask --app app seed-demo-users
```

Use `python3 seed.py` only when you want to reset the local SQLite database and
load the larger sample dashboard history. Copy `.env.example` to `.env` only if
you want to override settings such as `DATABASE_URL`, `SECRET_KEY`,
`ATIS_MODEL_PATH`, or `YOLO_DEVICE`.

Automatic number plate recognition uses `pytesseract` and requires the system
`tesseract` binary to be installed on hosts where plate OCR should run. If the
binary is missing, inspection uploads still work and the plate is marked for
ANPR review. Disable OCR with `ATIS_ANPR_ENABLED=0`; tune acceptance with
`ATIS_ANPR_MIN_CONFIDENCE` (default `55`). Sample OCR fixtures live in
`tests/fixtures/anpr_samples/`.

After installing Tesseract, run the local smoke/tuning helper:

```bash
python3 evaluate_anpr_samples.py
```

## Run The Dashboard

```bash
python3 app.py
```

Open:

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

Demo passwords are stored **hashed** (Werkzeug); the table above lists the
plaintext values only so you can log in to the local demo.

The `/predict` route uploads an image, auto-reads the license plate when the
plate field is blank, runs the trained classifier from
`runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`, stores an
inspection row, and creates an alert when the prediction is unsafe.

## Production Setup

Configuration is centralised in `config.py` and driven by environment variables.
For a production deployment set `ATIS_ENV=production` — the app then **refuses to
start without a strong `SECRET_KEY`**, disables demo seeding and demo login
aliases, and enables Secure session cookies.

```bash
export ATIS_ENV=production
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/atis_db
# Optional production image storage:
# export ATIS_IMAGE_STORAGE=s3
# export ATIS_S3_BUCKET=atis-inspection-images
# export ATIS_S3_SIGNED_URLS=1

python3 -m flask --app app db upgrade        # apply migrations (incl. password hashing)
python3 -m flask --app app create-admin      # create the first admin (hashed password)

gunicorn app:app                             # run behind a WSGI server (not app.py)
```

Security features active in every environment: hashed passwords, CSRF protection
on all form posts, login rate limiting, upload size cap + image content
validation, HTTPOnly/SameSite session cookies, and `debug` off unless
`FLASK_DEBUG=1`. See `.env.example` for all tunables.

Inspection images default to DB blob storage for demos. For production volume,
set `ATIS_IMAGE_STORAGE=s3` and configure an S3-compatible bucket; the database
then stores object keys and metadata instead of image bytes. S3 mode supports
object deletion helpers, optional signed media redirects, and configurable
client retry/timeout settings.

## CLI Model Commands

Prepare the dataset:

```bash
python3 prepare_dataset.py
```

Train:

```bash
python3 train_model.py
```

Set a device explicitly only when needed:

```bash
YOLO_DEVICE=0 python3 train_model.py
YOLO_DEVICE=cpu python3 train_model.py
```

Evaluate:

```bash
python3 evaluate_model.py
```

Run single-image inference:

```bash
python3 test_tyre.py
```

## Live Camera Inspection

The live workflow is Python-only and uses OpenCV windows, not a browser camera.
It assumes a fixed toll-booth camera position and calibrated tire scan zones.

Install dependencies, then calibrate zones:

```bash
python3 calibrate_live_zones.py --camera 0
```

In the calibration window:

- Drag one or more tire scan zones.
- Press `s` to save to `config/live_zones.json`.
- Press `c` to clear zones.
- Press `q` to quit without saving.

Run live inspection:

```bash
python3 live_video_inspection.py --camera 0
```

The dashboard also has a browser-camera live area at:

```text
http://127.0.0.1:5000/live
```

That page uses the operator device camera through the browser `getUserMedia`
API, posts sampled frames to `/api/live/analyze`, and can log a selected frame
through the existing `/predict` upload route. The standalone
`live_video_inspection.py` script remains available for server-side OpenCV
camera tests with calibrated fixed zones.

Runtime keys:

- `q` quits.
- `p` pauses or resumes analysis.
- `r` resets live streak counters.

Live dashboard defaults:

- Frames are analyzed roughly once per second while the camera is active.
- Live analysis is read-only; use "Capture & Log" to persist an inspection.
- Logged frames appear in dashboard history/alerts through the normal inspection flow.
- Configure live API limits with `ATIS_LIVE_FRAME_MAX_MB` and `ATIS_LIVE_FRAME_MAX_PIXELS`.

## Current Model Artifact

ATIS currently runs a **YOLOv11 classifier** trained for `normal` vs `cracked`.
The committed model card is at
`runs/classify/runs/classify/ATIS_Project/tyre_safety_model/model_card.json`.
The classifier gives the safety verdict:

- `normal` with confidence above `ATIS_CONF_THRESHOLD` -> dashboard status `safe`
- `cracked` / `crack` / `cracking` -> dashboard status `unsafe`, defect `Cracking`
- low-confidence `normal` -> dashboard status `unsafe`, manual review

When a tyre is classified as cracked, `atis_inference.py` uses a lightweight
OpenCV crack localizer to draw marker boxes over likely crack regions. Those
boxes are heuristic visual aids, not trained detector bounding boxes.

`train_detector.py` is present for a future YOLO detection model, but the web app
does not currently load detector weights or claim multi-defect detection. Do not
advertise `bulge`, `flat_spot`, or per-defect mAP metrics until the inference
path has been switched to a trained detector and evaluated honestly.

Threshold calibration and the current classifier-vs-detector decision are
documented in `docs/model_threshold_calibration.md`.

Dataset and model storage rules are documented in `docs/artifact_policy.md`.
In short: keep runtime weights that the app loads in Git LFS, and keep datasets,
dataset archives, scratch checkpoints, and generated training runs outside Git.

> Limitations: the current model only distinguishes normal vs cracked tyres in a
> single static image. Conditions such as under/over inflation are out of scope.

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
