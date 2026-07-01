# Deploying ATIS

The dashboard is a Flask app that lazy-loads a YOLOv11 classifier (torch, CPU).
It is packaged as a Docker image and served by gunicorn. This note covers the
build/run contract; the specific host is chosen separately.

## Prerequisites

- **Git LFS** — the classifier weights (`*.pt`) are stored via Git LFS. A plain
  `git clone` fetches 132-byte *pointer stubs*, not the real model. Always run:
  ```bash
  git lfs install      # once per machine
  git lfs pull         # download the real weights into the working tree
  ```
  The trained model lives at
  `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`.

## Build & run (Docker)

```bash
git lfs pull                                   # ensure real weights are present
docker build -t atis .                         # build fails early if weights are stubs
docker run --rm -p 8080:8080 \
  -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  -e ATIS_ENV=production \
  atis
```

The Dockerfile installs CPU-only torch (keeps the image small), copies the app,
and **fails the build** if `best.pt` is an LFS pointer stub — so a missing
`git lfs pull` is caught at build time, not at first inference.

### Required / useful runtime env vars

| Var | Purpose |
|-----|---------|
| `SECRET_KEY` | **Required in production** — app refuses to start without it (`ATIS_ENV=production`). |
| `ATIS_ENV` | `production` disables debug, demo seeding, and login aliases; enables secure cookies. |
| `DATABASE_URL` | Optional. Postgres DSN; falls back to SQLite at `instance/atis.db` if unset. |
| `PORT` | Port gunicorn binds (default `8080`; most PaaS inject this). |
| `WEB_CONCURRENCY` | Gunicorn workers. Keep at `1` unless the instance has ≥1 GB RAM *per extra* worker (each holds a full model copy). |

### First admin user (production)

Demo users only seed on SQLite in development. In production, create the first
admin explicitly:
```bash
ATIS_ENV=production flask --app app create-admin
```

## Sizing

torch + the model need **~1–2 GB RAM**; 512 MB tiers will OOM. One gunicorn
worker with threads is the default (`gunicorn.conf.py`, `preload_app=True` so the
model loads once and is shared copy-on-write).

## The Git-LFS gotcha, per host type

- **Build-locally-then-push (Cloud Run, Fly.io, any registry):** you run
  `git lfs pull` + `docker build` on a machine that has the real weights, so they
  are baked into the image. **Safe.**
- **Git-source PaaS that clones + builds remotely (e.g. Render/Railway git
  builds):** the remote builder must support Git LFS, or it will build from
  pointer stubs — and our Dockerfile guard will fail the build. Prefer pushing a
  prebuilt image, or confirm the platform fetches LFS objects.
- **Hugging Face Spaces (Docker):** Git LFS is native; the weights come down with
  the repo. **Safe.**

## Persistent data (not yet wired for production)

- `instance/atis.db` (SQLite) and `static/uploads/*` are ephemeral inside a
  container — lost on redeploy. For real deployments, point `DATABASE_URL` at
  managed Postgres and move uploads to object storage (e.g. S3/R2/Supabase).
