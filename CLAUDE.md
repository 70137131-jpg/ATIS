# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ATIS (Automated Tire Inspection System) couples a YOLOv11 nano **classifier**
(not a detector — it returns image-level class probabilities, no bounding boxes)
with a Flask operator dashboard for Pakistan's NHA. The classifier labels a tire
image as `normal` or `cracked`; the dashboard records each inspection, raises
alerts on unsafe results, and produces charts and PDF reports. The crack boxes
shown in the UI are OpenCV heuristic markers (`source:"heuristic"`, rendered
"(est.)"), **not** trained detector boxes — never present them as object detection.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run the dashboard (debug server on http://127.0.0.1:5000)
python3 app.py

# ML pipeline
python3 prepare_dataset.py      # "Tire Textures/" -> "ATIS_Dataset/" (Ultralytics layout)
python3 train_model.py          # trains the classifier, writes weights under ATIS_Project/
python3 evaluate_model.py       # top-1 accuracy + threshold sweep on ATIS_Dataset/val|test
python3 test_tyre.py            # single-image CLI inference (edit SAMPLE_IMAGE in the file)

# Force a device for training/inference (default: auto)
YOLO_DEVICE=0 python3 train_model.py     # also accepts: cpu, mps

# Database seeding (dev only — DROPS all tables; blocked in production)
python3 seed.py

# PostgreSQL (SQLite is the default; no setup needed for local dev)
cp .env.example .env            # set DATABASE_URL=postgresql+psycopg2://...
python3 -m flask --app app db upgrade
python3 migrate_sqlite_to_postgres.py            # copy SQLite rows into Postgres
python3 migrate_sqlite_to_postgres.py --replace  # only to overwrite existing Postgres rows

# First production admin (no demo seed in prod)
flask --app app create-admin

# Tests
python3 -m pytest

# Docker smoke build
docker build -t atis .
```

`test_tyre.py` is a CLI demo script, not a pytest test module.

## Architecture

**Inference is centralized in [atis_inference.py](atis_inference.py).** Both the
web app and CLI scripts call `classify_tyre_image()`. The YOLO model is
**lazy-loaded and cached** in module globals, so it loads once per process on
first prediction. Weights are resolved by `find_model_path()`, which checks
`ATIS_MODEL_PATH` first, then several relative candidates. The class→status
mapping is gated by an **asymmetric, fail-safe confidence threshold**
(`get_conf_threshold()`, env `ATIS_CONF_THRESHOLD`, default `0.60`): a tire is
passed as `safe` **only** when predicted `normal` *and* top-1 confidence ≥
threshold. A `cracked` prediction is `unsafe` at any confidence; a low-confidence
`normal` is downgraded to `unsafe` ("Low-confidence normal — manual review");
**any unexpected class is also `unsafe`**. A best-effort non-tyre gate
(contrast/edge-density, env `ATIS_FLAT_*`, optional COCO model) rejects obvious
non-tyre/blank frames. The model is a 2-class softmax, so the winning confidence
is always ≥ 0.50 — a threshold only bites above that.

**[app.py](app.py) owns the Flask app factory** (`create_app`) and extension
initialization. Routes are split under `routes/`
(`auth`, `inspections`, `live`, `alerts`, `reports`, `users`, `operations`,
`audit`), with shared decorators, role groups, and context helpers in
`routes/common.py`. Business logic lives in `services/`. Key flows:
- `/predict` (file upload) and `/api/live/analyze` (browser camera frames) funnel
  through the inspection service, which writes an `Inspection`, records
  `created_by_id`, stores upload metadata/checksum, and **when status is
  `unsafe`, auto-creates a pending `Alert`** in the same transaction.
- The `/api/reports/*` endpoints live in `routes/reports.py`; aggregation helpers
  live in `services/reports.py`; PDF/CSV and model-feedback ZIP exports are in
  `services/`. Chart.js is **self-hosted** at `static/js/vendor/chart.umd.min.js`
  (never a CDN — the CSP locks `script-src` to `'self'`).
- `inject_nha_status()` is a `context_processor` feeding pending-alert counts and
  recent alerts into every template (g-memoized + joinedload to keep it ~2 queries).

**Auth is session-based, with optional MFA.** Passwords are **hashed** with
Werkzeug (`User.set_password()` / `check_password()`) — never plaintext. Optional
**TOTP MFA** (`services/totp.py`) with one-time **recovery codes**
(`services/recovery_codes.py`) is enrolled at `/account/mfa` and verified at
`/mfa/verify`. **Login lockout/rate-limiting** lives in
`services/login_security.py`. User management is in `routes/users.py`.

**Security headers** are centralized in [security.py](security.py)
(`register_security_headers`, an `after_request` hook): CSP (which also carries
clickjacking defence via `frame-ancestors`), `X-Content-Type-Options`,
`Referrer-Policy`, `Permissions-Policy` (camera allowed for live feed), and HSTS
in production. `script-src` is `'self'` — **all JS/assets must be first-party**.
Framing is configurable via `ATIS_FRAME_ANCESTORS` (default `'self'`) because the
app is deliberately embedded cross-site on Hugging Face Spaces.

**Security config is centralised in [config.py](config.py)** and loaded via
`from_object`. `Config.validate()` **fails fast in production** (`ATIS_ENV=
production`) if `SECRET_KEY` is missing/default. CSRF (Flask-WTF) covers all form
POSTs. `/login`, `/predict`, `/api/live/analyze`, and ANPR preview are
rate-limited (Flask-Limiter). Uploads are capped (`MAX_CONTENT_LENGTH`) and
content-verified with PIL. Session cookies are HTTPOnly/SameSite (Secure +
SameSite=None in production for cross-site framing). `debug` is off unless
`FLASK_DEBUG`. **In production the WSGI stack is wrapped in `ProxyFix(x_for=1)`**
so `request.remote_addr` is the real client IP — audit logging trusts only
`remote_addr`, never the spoofable raw `X-Forwarded-For` header.

**Audit is tamper-evident** (`services/audit.py`): each `AuditEvent` is
hash-chained to its predecessor (`prev_hash` → `sha256`), so the append-only log
is verifiable. Timestamps are canonicalised to UTC-naive strings before hashing
to survive a SQLite round-trip.

**Async inference** (`services/inference_jobs.py`): predictions can be queued as
tracked jobs; the `processing.html` page polls for completion, decoupling upload
from model latency (`ATIS_INFERENCE_WORKERS`).

**Observability & ops:** `observability.py` (Sentry hooks), `metrics.py`
(Prometheus-style `/metrics`), `services/model_monitoring.py` (drift signals),
`services/retention.py` (data/audit pruning, `ATIS_RETENTION_DAYS` /
`ATIS_AUDIT_RETENTION_DAYS`), `services/cache.py` (stats caching,
`ATIS_STATS_CACHE_SECONDS`). `PUBLIC_ENDPOINTS` (the `before_request` auth
bypass) covers `login`, `mfa_verify`, `static`, `healthz`, `readyz`, and
`metrics` — so `/readyz` is fully unauthenticated and `/metrics` is too unless
`ATIS_METRICS_TOKEN` is set.

**[models.py](models.py)** defines `User`, `Inspection`, `Alert`, `AuditEvent`,
`DefectType`, `InspectionDefect`, MFA/recovery, inference-job, and operational
(location/camera) tables. New prediction writes use structured `InspectionDefect`
rows; the legacy `Inspection.defects` string is a backwards-compatible cache (use
the `defect_list` property).

**Database selection is automatic** ([config.py](config.py) `get_database_url`):
SQLite at `instance/atis.db` by default, Postgres if `DATABASE_URL` is set
(rewrites legacy `postgres://`). **Nothing is created or seeded at app startup** —
both backends get their schema from the Alembic migrations in `migrations/`
(currently through `0022`), so a fresh checkout needs `flask --app app db upgrade`.
Demo users are seeded only by the explicit `flask --app app seed-demo-users`
command (`ensure_demo_users()` in [app.py](app.py)), which `entrypoint.sh` runs
when `ATIS_SEED_DEMO=1`; it refuses to seed the well-known README passwords in
production unless `ATIS_DEMO_PASSWORD` is set. (`Config.SEED_DEMO_DATA` exists but
is currently read by nothing.) **Image storage** is DB blobs by default; optional
S3-compatible backend (`services/image_storage.py`) with signed URLs for production.

## Conventions

- **Datetimes are naive-UTC by convention.** Columns are `db.DateTime` without
  `timezone=True`; defaults call `datetime.now(timezone.utc)` and both SQLite and
  Postgres drop the tzinfo. Treat every stored datetime as UTC. Do NOT flip
  columns to `timezone=True` piecemeal — it must be one dedicated migration +
  code sweep. **(Still open — planned work.)**
- **Legacy string columns** (`Inspection.location`, `.camera`, `.defects`) are a
  write-through cache kept for old rows/reports; the structured versions
  (`location_id`, `camera_id`, `InspectionDefect`) are authoritative for new
  writes. Planned deprecation: stop reading the strings first, then drop columns
  in a later migration. **(Still open — planned work.)**
- **All front-end assets are first-party.** The CSP forbids external scripts;
  vendor JS is committed under `static/js/vendor/` and fonts under `static/fonts/`.

## Gotchas

- **Demo login aliases:** the README advertises `*@nha.gov.pk` accounts, but the
  seeded users are `*@atis.com`; `login()` maps them. Aliases are disabled in
  production (`ATIS_DEMO_ALIASES`).
- **Demo credentials/passwords in prod:** demo seeding requires `ATIS_DEMO_PASSWORD`
  and won't use README passwords in production; the login-page credentials box is
  gated by `ATIS_SHOW_DEMO_CREDENTIALS` (off in prod).
- **`seed.py` DROPS ALL TABLES** and is hard-blocked when `ATIS_ENV=production`
  (override only with `ATIS_ALLOW_SEED=1`).
- **Weights location vs. README:** `train_model.py` sets `project="ATIS_Project"`;
  the inference resolver also checks `runs/classify/...`, so both layouts work.
  Runtime weights live in **Git LFS** (doubly-nested
  `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`).
- **Artifact policy:** runtime weights stay in Git LFS; datasets, zips, scratch
  checkpoints, and training runs stay outside the repo (see `docs/artifact_policy.md`).
- `instance/` (SQLite DB), `static/uploads/*`, and `.coverage` are gitignored.

## Deployment

Docker + gunicorn (`gunicorn.conf.py`), port 8080. Deployed to **Hugging Face
Spaces** (Docker SDK); DigitalOcean docs also exist. HF free-tier storage is
ephemeral (SQLite/uploads reset on rebuild) — add Neon Postgres via `DATABASE_URL`
and S3 for persistence. Before any HF deploy, set `SECRET_KEY`, `ATIS_ENV=production`,
and `ATIS_DEMO_PASSWORD`. See [DEPLOY.md](DEPLOY.md) for the go-live checklist;
compliance docs (DPIA, privacy, data/model governance) are under `docs/`.
Live camera works locally only (cloud Spaces have no webcam).
