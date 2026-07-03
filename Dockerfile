# ATIS (Flask + YOLOv11 classifier) production image.
FROM python:3.12-slim

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
# torchvision already satisfied and skips them.
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application. .dockerignore keeps the multi-GB dataset and git
# history out of the build context; only code + the model weights ship.
COPY . .

# Fallback for deploy platforms where Git-LFS isn't pulled before build (e.g.
# App Platform). The classifier is required; the COCO object model is optional
# and only improves obvious non-tyre rejection.
RUN CLASSIFIER="runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt"; \
    if [ ! -f "$CLASSIFIER" ]; then \
      echo "ERROR: classifier weights not found: $CLASSIFIER"; exit 1; \
    fi; \
    if head -c 64 "$CLASSIFIER" | grep -q "git-lfs"; then \
      echo "WARNING: $CLASSIFIER is a Git-LFS pointer stub. Downloading real weights from GitHub..."; \
      curl -L -o "$CLASSIFIER" "https://github.com/70137131-jpg/ATIS/raw/main/$CLASSIFIER" || exit 1; \
    fi; \
    echo "Classifier weights OK: $CLASSIFIER ($(wc -c < "$CLASSIFIER") bytes)"; \
    OBJECT_MODEL="yolo26n.pt"; \
    if [ -f "$OBJECT_MODEL" ]; then \
      if head -c 64 "$OBJECT_MODEL" | grep -q "git-lfs"; then \
        echo "WARNING: $OBJECT_MODEL is a Git-LFS pointer stub. Downloading real weights from GitHub..."; \
        curl -L -o "$OBJECT_MODEL" "https://github.com/70137131-jpg/ATIS/raw/main/$OBJECT_MODEL" || true; \
      fi; \
      echo "Object-gate weights OK: $OBJECT_MODEL ($(wc -c < "$OBJECT_MODEL") bytes)"; \
    else \
      echo "WARNING: optional object-gate weights not found: $OBJECT_MODEL"; \
    fi

EXPOSE 8080

# Production startup: run migrations, optionally create admin, then start gunicorn.
# Set ATIS_ADMIN_EMAIL + ATIS_ADMIN_PASSWORD env vars on first deploy to auto-create
# an admin user. SECRET_KEY must be supplied at runtime or the app refuses to start.
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
