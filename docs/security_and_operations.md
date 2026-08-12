# ATIS Security & Operations

What is implemented for the security/observability hardening, how to operate it,
and what is deliberately left for a later phase.

## Implemented

### Security headers (`security.py`)
Every response carries a Content-Security-Policy (with `frame-ancestors` for
clickjacking defence), `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
`Permissions-Policy`, and — in production — HSTS.

- Framing is configurable via `ATIS_FRAME_ANCESTORS` (default `'self'`). When
  embedding in a cross-site iframe (Hugging Face Spaces), set it to the parent,
  e.g. `'self' https://*.hf.space https://huggingface.co`.
- The full CSP can be overridden with `ATIS_CSP` if a deployment needs custom
  sources. The default is entirely first-party — `script-src`, `font-src`, and
  `style-src` are all `'self'` (see "Self-hosted fonts" below), so no external
  origin is reachable. `style-src` additionally carries `'unsafe-inline'` for the
  inline `style="…"` attributes in the templates; removing those attributes is
  what it would take to drop it. `img-src` also allows `data:` for inline
  previews.

### Account lockout (`services/login_security.py`)
Per-**account** throttle that complements the per-**IP** login rate limit: after
`ATIS_MAX_LOGIN_ATTEMPTS` (default 5) consecutive failures the account locks for
`ATIS_LOCKOUT_MINUTES` (default 15). A successful login clears it. The lock is
checked before the password so a locked account cannot be probed, and login
events (`auth.login_succeeded` / `_failed` / `_locked`) are audited.

### Password policy (`services/passwords.py`)
One shared policy for admin-create, admin-reset, and self-change: minimum length
`ATIS_MIN_PASSWORD_LENGTH` (default 12), a built-in weak/common block-list, a
no-username rule, and a light character-variety requirement.

### Session revocation (`users.session_epoch`)
Signed-cookie sessions are still used, but each carries a `session_epoch`.
Bumping a user's epoch (on password change or admin reset) invalidates all their
existing sessions — the "logout everywhere" the app previously could not do. On
login the session is also regenerated (session-fixation defence).

### Readiness probe (`/readyz`)
`/healthz` stays a cheap liveness probe (process up). `/readyz` checks the real
dependencies — a DB round-trip, and model resolvability under warmup — and
returns 503 when not ready, so a load balancer stops routing to an instance
whose DB is down or whose migrations have not run. Point the platform health
check at `/readyz` (the DigitalOcean spec does).

### Structured logging (`observability.py`)
Set `ATIS_LOG_JSON=1` for JSON logs with a per-request correlation id. The
inbound `X-Request-ID` is honoured (or one is minted) and echoed back, so a trace
id flows from the edge through the logs.

### Two-factor authentication (`services/totp.py`, `services/recovery_codes.py`)
Optional per-user TOTP (RFC 6238, standard-library only — works with Google
Authenticator, Authy, 1Password). A user enables it at `/account/mfa` (scan the
key / paste the `otpauth://` URI, confirm a code). When enabled, login requires
the code at `/mfa/verify` after the password; MFA failures feed the same
per-account lockout, and enabling it bumps `session_epoch` to re-auth other
sessions. Enrolment and the second-factor step are audited
(`user.mfa_enabled/_disabled`, `auth.mfa_succeeded/_failed`).

Enabling MFA also issues **single-use recovery codes** (shown once, stored
hashed). A recovery code is accepted in place of a TOTP code at `/mfa/verify` and
is consumed on use (`auth.mfa_recovery_used`); codes can be regenerated from
`/account/mfa`. This prevents a lost authenticator from locking a user out.

### Caching (`services/cache.py`)
A tiny per-process TTL cache for the heavier dashboard/report aggregations,
enabled with `ATIS_STATS_CACHE_SECONDS` (0 = off, live results). Bounded
staleness only — never used for read-your-writes data.

### Accessibility (WCAG)
A baseline pass toward WCAG 2.1 AA: a keyboard **skip-to-content** link and a
focusable `#main-content` landmark; `aria-current="page"` on the active nav item;
decorative icons marked `aria-hidden`/`focusable="false"` (the icon macro, so it
applies everywhere); `scope="col"` on all data-table headers; flash messages in a
`role="status" aria-live="polite"` region so they are announced; and a visible
`:focus-visible` keyboard focus indicator. Not a full audit — colour-contrast
verification and a screen-reader pass on every flow still remain.

### Self-hosted fonts
The Outfit (app) and Inter (login) fonts are served from `static/fonts/` via
`static/css/fonts.css` instead of Google Fonts, so there is no external font
request. This removes a third-party dependency/privacy leak and lets the CSP
`style-src`/`font-src` stay first-party (`'self'`).

### Prometheus metrics (`/metrics`)
Dependency-free Prometheus exposition of database-derived gauges: inspection mix,
recent unsafe rate, pending alerts, average inference latency, active users, and
async job backlog. Public by default (put it behind network policy) or require
`Authorization: Bearer <ATIS_METRICS_TOKEN>`. Point a Prometheus scrape at it and
alert on, e.g., `atis_alerts_pending` or `atis_inference_jobs{status="error"}`.

### Tamper-evident audit log (`services/audit.py`)
Each `audit_events` row stores `entry_hash` = SHA-256 over its content plus the
previous row's hash, forming a chain. Editing or deleting any row breaks the
chain from that point, which the verifier detects:

```bash
flask --app app atis-verify-audit   # exits non-zero and names the first broken row
```

Rows written before this feature keep NULL hashes and are reported as
`legacy_unchained`. This is *detection*, not prevention (a DB admin can still
rewrite the whole chain), and it assumes serialized audit writes — fine for the
default single worker; a multi-writer deployment should serialize audit writes or
ship to an append-only sink. Schedule `atis-verify-audit` (e.g. daily) to alert
on tampering.

### CI security gates (`.github/`)
- `dependabot.yml`: weekly pip, GitHub-Actions, and Docker base-image updates.
- `pip-audit` job: scans pinned dependencies for known CVEs (report-only for now).
- Trivy image scan in the docker-smoke job (HIGH/CRITICAL, report-only for now).
- Coverage floor (`--cov-fail-under=68`) so the safety net can't silently erode.
- Migration downgrade→upgrade round-trip, so every rollback path is exercised.

> The two vulnerability scans are report-only (they do not fail the build yet) so
> a newly-disclosed CVE surfaces without blocking unrelated work. Flip
> `pip-audit … || true` and Trivy `exit-code: "1"` to enforce once the initial
> findings are triaged.

### Async (background) inference
Enable with `ATIS_ASYNC_INFERENCE=1`. `POST /predict` then saves the upload,
records an `inference_jobs` row, and returns a job id immediately (202 for XHR, a
polling page for form posts) while a bounded in-process thread pool
(`ATIS_INFERENCE_WORKERS`, default 1) runs the slow model call and persists the
Inspection. The UI polls `/jobs/<id>`. No broker or separate worker process, so
it fits the single-container default; the tradeoff is that an in-flight job is
lost if the process is killed (it stays `running` — never falsely `done`). Off by
default, so the synchronous path and its behaviour are unchanged unless enabled.

## Not yet done (next phase, roughly in priority order)

- **Server-side session store** (Redis/DB) for full, immediate revocation and to
  reduce reliance on `SECRET_KEY` secrecy. `session_epoch` covers revocation for
  now; it does not remove the signed-cookie trust model.
- **Distributed task queue** (Celery/RQ + Redis) — only if you outgrow the
  in-process pool and need cross-instance queuing or crash-safe job durability.
- **Dashboards/alert rules** wired to `/metrics` (endpoint is implemented).
- **CD pipeline**: a staging environment, post-deploy smoke test, and automated
  rollback instead of `deploy_on_push` straight to production.
- **Secrets manager** integration rather than plaintext env values in specs.
- **E2E/browser tests** — the suite is server-side (`pytest` against the Flask
  test client); no browser driver exercises the upload, live-feed, or MFA flows
  end to end.
- **WCAG accessibility** — the baseline pass is described under "Accessibility"
  above; colour-contrast verification and a screen-reader pass on every flow are
  still outstanding.
- **i18n / Urdu** — not started; all template copy is hard-coded English.
