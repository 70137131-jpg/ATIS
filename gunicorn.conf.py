"""Gunicorn config for the ATIS dashboard.

Tuned for small (1 GB) cloud instances: the YOLO/torch model holds ~0.5-1 GB of
RAM per worker, so we run a single worker with threads for concurrency and
preload the app so the model is loaded (and validated, via ATIS_WARMUP) once.
"""

import os

# PaaS platforms (DigitalOcean App Platform, Heroku, etc.) inject $PORT;
# fall back to 8080 for local `docker run`.
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Raise WEB_CONCURRENCY only on instances with enough RAM for another full
# copy of the model (~1 GB each).
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# Load the app in the master before forking so the model is loaded once and
# shared copy-on-write, and a broken model fails the deploy at boot.
preload_app = True

# Model load + first inference can take a while; don't let the master reap a
# worker mid-request.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30

# Log to stdout/stderr so the platform captures it.
accesslog = "-"
errorlog = "-"
