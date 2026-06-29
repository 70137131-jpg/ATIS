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

# Ali kindly run the command : "pip install ultralytics torch torchvision" before running any training script in local enviornment.
# yolo classify train resume model=E:\ATIS\runs\classify\ATIS_Project\tyre_safety_model\weights\last.pt workers=2 (Run this command in CLI interfacecase you get memory error crash don't restart the whole script)
