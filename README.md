# Automated Tire Detection and Inspection System (ATIS)

ATIS is a final-year project prototype for tire safety screening at highway or toll entry points. The system is planned as a Flask web application that allows operators to upload or simulate tire image capture, run image preprocessing and tire-condition classification, generate alerts for unsafe or uncertain tires, and review inspection history and reports.

The current source of truth is [PROD_Flask_ATIS.md](PROD_Flask_ATIS.md).

## Current Status

This repository is currently prepared as a clean Flask project scaffold only. Feature implementation has not started yet.

Implemented so far:

- Flask monolith folder structure
- Jinja2 template folders
- Static asset and upload folders
- AI model workspace
- Migration, test, script, docs, and instance folders
- Project structure documentation

Not implemented yet:

- Flask app factory
- Database models
- Authentication
- Image upload workflow
- OpenCV preprocessing
- Mock or real classifier
- Alerts, reports, and admin screens

## Planned Stack

- Web framework: Flask
- Frontend rendering: Jinja2 templates
- UI styling: Bootstrap 5 and custom CSS
- Database: SQLite for the local prototype
- ORM: Flask-SQLAlchemy / SQLAlchemy
- Authentication: Flask-Login and Werkzeug password hashing
- Image processing: OpenCV, NumPy, Pillow
- AI model: TensorFlow/Keras CNN with mock classifier fallback
- Charts: Chart.js
- Environment config: Python-dotenv

## Repository Structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for the current scaffold.

High-level layout:

```text
ATIS/
|-- app/
|-- ai_model/
|-- migrations/
|-- tests/
|-- docs/
|-- instance/
|-- scripts/
|-- requirements.txt
|-- run.py
|-- README.md
|-- PROD.md
|-- PROD_Flask_ATIS.md
`-- PROJECT_STRUCTURE.md
```

## MVP Direction

The MVP will prioritize:

- Login for operators and admins
- Dashboard rendered with Flask/Jinja2
- Tire image upload
- OpenCV preprocessing
- Mock classifier fallback first
- TensorFlow/Keras model loading later
- Alert creation and acknowledgement
- Inspection history and detail pages
- Basic reports with charts

ATIS is a decision-support tool for human review. It does not automatically issue fines or replace manual safety inspection.

## Local Setup

These commands are for Windows PowerShell from the repository root.

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a local environment file when configuration is added:

```powershell
Copy-Item .env.example .env
```

If `.env.example` does not exist yet, create `.env` later when the Flask config is implemented. Never commit `.env`.

## Running The Flask App

The app is still a scaffold, so it is not runnable yet. After the Flask app factory is implemented, the expected local command will be:

```powershell
flask --app run run --debug
```

If `run.py` is later configured as an executable entry point, this may also work:

```powershell
python run.py
```

## Basic Git Workflow

Use feature branches instead of committing directly to `main`.

```powershell
git switch dev
git pull origin dev
git switch -c feature/example-name
```

See [DEVOPS.md](DEVOPS.md) for the full branch strategy, prompt-to-branch mapping, before-push checklist, merge rules, and Git command examples.
