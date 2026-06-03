# Drive IQ / ATIS

Automated Tire Inspection System (ATIS) now combines the trained YOLO tire
classifier with the NHA operator dashboard in one Flask application.

The repository contains:

- A YOLO classification dataset for `cracked` and `normal` tire images.
- Training, evaluation, and single-image CLI scripts.
- A Flask dashboard with login, inspection uploads, history, alerts, reports,
  PDF export, and database models.
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

The app defaults to the included SQLite database at `instance/atis.db`. Copy
`.env.example` to `.env` only if you want to override settings such as
`DATABASE_URL`, `SECRET_KEY`, `ATIS_MODEL_PATH`, or `YOLO_DEVICE`.

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

The `/predict` route uploads an image, runs the trained classifier from
`runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`, stores an
inspection row, and creates an alert when the prediction is unsafe.

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

## Current Model Artifact

The included run was trained for 50 epochs. The last logged top-1 validation
accuracy is about 82.46%, with the best logged top-1 accuracy about 83.39%.

The current classifier labels only two classes:

- `normal` -> dashboard status `safe`
- `cracked` -> dashboard status `unsafe`, defect `Cracking`

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
