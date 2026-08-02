# ATIS (Flask + YOLOv11 classifier) production image.
FROM python:3.14-slim

# OpenCV (opencv-python) loads these shared libs on import even when the live
# camera UI is unused; every other dependency ships as a manylinux wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ATIS_ENV=production \
    ATIS_WARMUP=1 \
    PORT=8080

WORKDIR /app

# Install the CPU-only Torch build first so the multi-GB CUDA wheels are never
# pulled (keeps the image far smaller). requirements.txt then sees torch and
# torchvision already satisfied and skips them. constraints.txt pins the exact
# versions so builds are reproducible. PyPI stays available as the extra index
# because torch's transitive deps (filelock, sympy, ...) are constrained to
# versions the PyTorch index doesn't host; the +cpu torch/torchvision builds
# still win the resolve because a local version sorts above the plain release.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application. .dockerignore keeps the multi-GB dataset and git
# history out of the build context; only code + the model weights ship.
COPY . .

# Fallback for deploy platforms where Git-LFS isn't pulled before build (e.g.
# App Platform). The classifier is required; the COCO object model is optional
# and only improves obvious non-tyre rejection. Every artifact — whether it came
# from the build context or the fallback download — must match its pinned
# SHA256, so a tampered or corrupted model can never ship.
ENV ATIS_CLASSIFIER_SHA256=8d27d1de6823436fa29ff5c3082276b96d9dc37eee5e3af5ac1f3c8e8bfba5e0 \
    ATIS_OBJECT_MODEL_SHA256=9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef
RUN CLASSIFIER="runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt"; \
    if [ ! -f "$CLASSIFIER" ]; then \
      echo "ERROR: classifier weights not found: $CLASSIFIER"; exit 1; \
    fi; \
    if head -c 64 "$CLASSIFIER" | grep -q "git-lfs"; then \
      echo "WARNING: $CLASSIFIER is a Git-LFS pointer stub. Downloading real weights from GitHub..."; \
      curl -L -o "$CLASSIFIER" "https://github.com/70137131-jpg/ATIS/raw/main/$CLASSIFIER" || exit 1; \
    fi; \
    echo "$ATIS_CLASSIFIER_SHA256  $CLASSIFIER" | sha256sum -c - \
      || { echo "ERROR: classifier weights failed SHA256 verification."; exit 1; }; \
    echo "Classifier weights OK: $CLASSIFIER ($(wc -c < "$CLASSIFIER") bytes)"; \
    OBJECT_MODEL="yolo26n.pt"; \
    if [ -f "$OBJECT_MODEL" ]; then \
      if head -c 64 "$OBJECT_MODEL" | grep -q "git-lfs"; then \
        echo "WARNING: $OBJECT_MODEL is a Git-LFS pointer stub. Downloading real weights from GitHub..."; \
        curl -L -o "$OBJECT_MODEL" "https://github.com/70137131-jpg/ATIS/raw/main/$OBJECT_MODEL" || true; \
      fi; \
      if echo "$ATIS_OBJECT_MODEL_SHA256  $OBJECT_MODEL" | sha256sum -c -; then \
        echo "Object-gate weights OK: $OBJECT_MODEL ($(wc -c < "$OBJECT_MODEL") bytes)"; \
      else \
        echo "WARNING: $OBJECT_MODEL failed SHA256 verification — removing it."; \
        echo "WARNING: the optional non-tyre object gate will be disabled in this image."; \
        rm -f "$OBJECT_MODEL"; \
      fi; \
    else \
      echo "WARNING: optional object-gate weights not found: $OBJECT_MODEL"; \
    fi

# Run as a dedicated non-root user. Only the runtime-writable paths are chowned:
# instance/ (SQLite fallback) and static/uploads/ (legacy upload path).
RUN useradd --create-home --uid 1000 atis \
    && mkdir -p /app/instance /app/static/uploads \
    && chmod +x /app/entrypoint.sh \
    && chown -R atis:atis /app
USER atis
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics \
    MPLCONFIGDIR=/tmp/matplotlib

EXPOSE 8080

# Container-level liveness probe against the unauthenticated /healthz endpoint.
# start-period covers model warmup + migrations on slow 1 GB instances.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/healthz" || exit 1

# Production startup: run migrations, optionally create admin, then start gunicorn.
# Set ATIS_ADMIN_EMAIL + ATIS_ADMIN_PASSWORD env vars on first deploy to auto-create
# an admin user. SECRET_KEY must be supplied at runtime or the app refuses to start.
# entrypoint.sh ships via `COPY . .` above and is chmod'd during user setup.
CMD ["./entrypoint.sh"]
