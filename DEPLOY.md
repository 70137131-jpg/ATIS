# Deploying ATIS

The dashboard is a Flask app that lazy-loads a YOLOv11 classifier (torch, CPU).
It is packaged as a Docker image and served by gunicorn. This note covers the
build/run contract; the specific host is chosen separately.

## Production go-live checklist

Deploying the container is not the same as being production-ready. Before
trusting verdicts from a real checkpoint, work through every line:

**Scope (what this system is)**
- [ ] Stakeholders know the model is a binary `normal` vs `cracked` **classifier**.
      The overlay boxes are heuristic OpenCV visual markers, not trained
      detections. Do not promise bulge, puncture, flat-spot, inflation,
      tread-depth, or per-defect localization — see `model_card.json`
      `known_limitations` and README "Model scope".

**Model evidence**
- [ ] Held-out test metrics (cracked recall, false-pass rate, false-flag rate,
      confusion matrix, threshold sweep) are recorded in `model_card.json`
      (`test_metrics`). Re-run `evaluate_model.py` after any retrain.
- [ ] **Field validation on the target cameras** — the training data is mostly
      controlled/web imagery. Pilot on the real checkpoint feed and measure
      recall/false-flag across: day + night (with checkpoint lighting), wet and
      dirty tyres, motion blur, partial tyres in frame, different vehicle
      classes, shadows/glare, and deliberate non-tyre inputs. Do not enforce
      verdicts until this data exists.

**Persistence & data**
- [ ] `DATABASE_URL` points at managed PostgreSQL (SQLite in a container is
      ephemeral and single-writer).
- [ ] `ATIS_IMAGE_STORAGE=s3` with `ATIS_S3_BUCKET` (DB-blob storage is a demo
      default; images bloat Postgres fast).
- [ ] Automated DB backups are enabled **and a restore has been rehearsed once**.
- [ ] A retention/deletion policy exists for inspection images and audit rows
      (they contain plates and IP addresses — that is personal data).

**Runtime**
- [ ] `SECRET_KEY` set (the app refuses to boot without it), `ATIS_ENV=production`.
- [ ] Demo seeding OFF (`ATIS_SEED_DEMO` unset) — or, for a demo host, set
      `ATIS_DEMO_PASSWORD`. The login-page credentials box is hidden in
      production unless `ATIS_SHOW_DEMO_CREDENTIALS=1`.
- [ ] If `WEB_CONCURRENCY > 1` or more than one instance: point
      `RATELIMIT_STORAGE_URI` at Redis. In-memory counters are per-process, so
      effective rate limits multiply per worker.
- [ ] The Docker image builds green in CI (`docker-smoke` job); if you changed
      the Dockerfile, also run `docker build -t atis .` locally once.

## Prerequisites

- **Git LFS** — the classifier weights (`*.pt`) are stored via Git LFS. A plain
  `git clone` fetches 132-byte *pointer stubs*, not the real model. Always run:
  ```bash
  git lfs install      # once per machine
  git lfs pull         # download the real weights into the working tree
  ```
  The trained model lives at
  `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`.
  Dataset archives and scratch training artifacts are not deployment inputs; see
  `docs/artifact_policy.md`.

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
and **fails the build** if the required classifier `best.pt` is missing or still
an LFS pointer stub after the fallback download.

### Required / useful runtime env vars

| Var | Purpose |
|-----|---------|
| `SECRET_KEY` | **Required in production** — app refuses to start without it (`ATIS_ENV=production`). |
| `ATIS_ENV` | `production` disables debug, demo seeding, and login aliases; enables secure cookies. |
| `DATABASE_URL` | Optional. Postgres DSN; falls back to SQLite at `instance/atis.db` if unset. |
| `PORT` | Port gunicorn binds (default `8080`; most PaaS inject this). |
| `WEB_CONCURRENCY` | Gunicorn workers. Keep at `1` unless the instance has ≥1 GB RAM *per extra* worker (each holds a full model copy). |
| `ATIS_IMAGE_STORAGE` | `db` by default. Use `s3` for S3-compatible object storage. |
| `ATIS_S3_BUCKET` | Required when `ATIS_IMAGE_STORAGE=s3`. |
| `ATIS_S3_REGION` / `ATIS_S3_ENDPOINT_URL` | Optional S3-compatible region/endpoint values, e.g. DigitalOcean Spaces or R2. |
| `ATIS_S3_SIGNED_URLS` / `ATIS_S3_SIGNED_URL_EXPIRES` | Optional. Redirect media requests to temporary S3 URLs; default disabled, expiry `900` seconds. |
| `ATIS_S3_CONNECT_TIMEOUT` / `ATIS_S3_READ_TIMEOUT` | Optional S3 client timeouts; defaults `3` and `10` seconds. |
| `ATIS_S3_MAX_ATTEMPTS` / `ATIS_S3_RETRY_MODE` | Optional S3 retry config; defaults `3` attempts and `standard` mode. |

### First admin user (production)

Demo users are never created by importing the app. In production, create the
first admin explicitly:
```bash
ATIS_ENV=production flask --app app create-admin
```

## Sizing

torch + the model need **~1–2 GB RAM**; 512 MB tiers will OOM. One gunicorn
worker with threads is the default (`gunicorn.conf.py`, `preload_app=True` so the
model loads once and is shared copy-on-write).

## Deploy to DigitalOcean App Platform

The repository includes a DigitalOcean App Platform spec template at
`.do/app.yaml.example`. It deploys the existing Dockerfile from GitHub, binds
the service on port `8080`, provisions a PostgreSQL database, and runs one
2 GB container because the app loads torch and YOLO weights in memory.

1. Make sure `main` is pushed to GitHub:
   ```bash
   git push origin main
   git lfs push origin main
   ```
2. Copy the template to a local, untracked spec and replace the two secret
   placeholders:
   ```bash
   cp .do/app.yaml.example /tmp/atis-do-app.yaml
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   ```
   Set `SECRET_KEY` to the generated value, and set
   `ATIS_ADMIN_PASSWORD` to the password for the first admin account.
3. Create the app:
   ```bash
   doctl apps create --spec /tmp/atis-do-app.yaml
   ```
4. Watch the deployment:
   ```bash
   doctl apps list
   doctl apps get <app-id>
   doctl apps logs <app-id> web --type build --follow
   doctl apps logs <app-id> web --type run --follow
   ```

The app will be available on its default `.ondigitalocean.app` domain after the
deployment becomes live. Log in with the `ATIS_ADMIN_EMAIL` and
`ATIS_ADMIN_PASSWORD` values from the spec. (Demo accounts only seed in
production when `ATIS_SEED_DEMO=1` **and** `ATIS_DEMO_PASSWORD` are set — they
get that password, never the README ones.)

Notes:
- App Platform uses the GitHub repo as the build source. The Dockerfile can
  recover if Git LFS pointers are present by downloading the classifier weights
  from GitHub's raw endpoint.
- The included database is a development PostgreSQL database. For a long-running
  production install, switch the spec to a production DigitalOcean Managed
  PostgreSQL cluster and keep using `DATABASE_URL`.
- Uploaded inspection images default to DB storage for demo durability. Set
  `ATIS_IMAGE_STORAGE=s3` to keep only object metadata in Postgres and store the
  bytes in S3-compatible object storage.

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

## Persistent Data

- `instance/atis.db` is ephemeral inside a container. For real deployments,
  point `DATABASE_URL` at managed Postgres.
- Uploaded images are stored as DB blobs by default so demo rebuilds do not lose
  the image bytes. For production volume, set `ATIS_IMAGE_STORAGE=s3` and provide
  `ATIS_S3_BUCKET` plus optional `ATIS_S3_REGION`, `ATIS_S3_ENDPOINT_URL`, and
  `ATIS_IMAGE_PREFIX`; the app then stores object metadata in Postgres and serves
  bytes through `/media/inspection/<id>`.

## Deploy to Hugging Face Spaces (Docker) — recommended for the demo

HF Spaces builds the Dockerfile for you, has Git LFS native (weights just work),
and the free CPU tier has 16 GB RAM (torch fits easily). The `README.md`
frontmatter (`sdk: docker`, `app_port: 8080`) tells HF how to build/route it.

1. Create a free account at https://huggingface.co, then **New Space** →
   SDK **Docker** → choose blank/empty template. Note the git URL:
   `https://huggingface.co/spaces/<user>/<space>`.
2. Push this repo to the Space (Git LFS uploads the weights automatically):
   ```bash
   git remote add space https://huggingface.co/spaces/<user>/<space>
   git push space main:main
   ```
   Authenticate with an HF **access token** (Settings → Access Tokens, "write").
3. In the Space UI → **Settings → Variables and secrets**, set:
   | Name | Kind | Value |
   |------|------|-------|
   | `SECRET_KEY` | secret | a long random string (`python3 -c 'import secrets;print(secrets.token_hex(32))'`) |
   | `ATIS_ENV` | variable | `production` |
   | `ATIS_SEED_DEMO` | variable | `1`  ← seeds the demo accounts |
   | `ATIS_DEMO_PASSWORD` | **secret** | the password every demo account gets. **Required in production** — without it the app refuses to seed the well-known README passwords (they would be a public backdoor). |
4. The Space builds, then serves the full dashboard at
   `https://<user>-<space>.hf.space`. Log in with `admin@atis.com` and your
   `ATIS_DEMO_PASSWORD`.

   If an earlier deploy already created `admin@atis.com` with the old `admin123`
   password (persistent DB), rotate it by setting `ATIS_ADMIN_EMAIL=admin@atis.com`
   and `ATIS_ADMIN_PASSWORD=<new password>` — the entrypoint's `create-admin`
   updates the existing user's password on boot.

Notes:
- **Data is ephemeral** on the free tier (SQLite + uploads reset when the Space
  rebuilds/restarts). Fine for a demo; add Neon Postgres via `DATABASE_URL` for
  persistence.
- **Live camera does not work in the cloud** — the Space has no webcam. Run the
  live-feed demo locally; the cloud Space handles image-upload inspection.
