# ATIS Flask Project Structure

This repository is now prepared for the Flask-based Automated Tire Detection and Inspection System prototype described in `PROD_Flask_ATIS.md`.

The project is a Flask monolithic web application. Flask will handle backend logic, database access, authentication, image upload, AI inference workflow, and server-rendered frontend pages using Jinja2 templates.

```text
ATIS/
|-- app/
|   |-- __init__.py
|   |-- config.py
|   |-- extensions.py
|   |-- models/
|   |   |-- __init__.py
|   |   |-- user.py
|   |   |-- vehicle.py
|   |   |-- tire.py
|   |   |-- inspection.py
|   |   |-- prediction.py
|   |   `-- alert.py
|   |-- routes/
|   |   |-- __init__.py
|   |   |-- auth_routes.py
|   |   |-- dashboard_routes.py
|   |   |-- inspection_routes.py
|   |   |-- alert_routes.py
|   |   |-- report_routes.py
|   |   |-- admin_routes.py
|   |   `-- api_routes.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- preprocessing_service.py
|   |   |-- classifier_service.py
|   |   |-- mock_classifier.py
|   |   |-- alert_service.py
|   |   |-- report_service.py
|   |   `-- anpr_service.py
|   |-- templates/
|   |   |-- base.html
|   |   |-- auth/
|   |   |-- dashboard/
|   |   |-- inspections/
|   |   |-- alerts/
|   |   |-- reports/
|   |   `-- admin/
|   |-- static/
|   |   |-- css/
|   |   |-- js/
|   |   `-- uploads/
|   |       |-- original/
|   |       `-- processed/
|   `-- utils/
|-- ai_model/
|   |-- models/
|   |-- notebooks/
|   `-- training/
|-- migrations/
|-- tests/
|-- docs/
|   `-- diagrams/
|-- instance/
|-- scripts/
|-- requirements.txt
|-- run.py
|-- README.md
|-- PROD.md
|-- PROD_Flask_ATIS.md
`-- PROJECT_STRUCTURE.md
```

## Folder Purpose

- `app/`: Main Flask application package.
- `app/models/`: SQLAlchemy database models for users, vehicles, tires, inspections, predictions, and alerts.
- `app/routes/`: Flask route modules for auth, dashboard, inspections, alerts, reports, admin, and small JSON endpoints.
- `app/services/`: Business logic for preprocessing, classification, alerts, reports, and mock ANPR.
- `app/templates/`: Jinja2 templates for the server-rendered UI.
- `app/static/`: Bootstrap/custom CSS, JavaScript, and uploaded/processed inspection images.
- `app/utils/`: Reusable helpers for files, security, validation, and shared utilities.
- `ai_model/`: Saved model files, notebooks, and training work kept outside the web app.
- `migrations/`: Flask-Migrate/Alembic migrations when database migrations are added.
- `tests/`: Unit and integration tests.
- `docs/`: Architecture diagrams, user manual, model notes, and final-year documentation.
- `instance/`: Local SQLite database and private runtime files.
- `scripts/`: Utility scripts such as creating the first admin user or seeding demo data.

## Current Implementation Rule

This scaffold intentionally contains no feature implementation yet. The next implementation phase should start with the Flask app factory, configuration, extensions, database models, and authentication.
