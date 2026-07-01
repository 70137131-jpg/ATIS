# ATIS (Flask + YOLOv11 classifier) production image.
FROM python:3.12-slim

# OpenCV (opencv-python) loads these shared libs on import even when the live
# camera UI is unused; every other dependency ships as a manylinux wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
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

# Fail fast if the classifier weights are a Git-LFS pointer stub (~132 bytes)
# instead of the real file. This happens when the image is built from a fresh
# clone without `git lfs pull` — the app would otherwise boot and crash at the
# first inference. Building locally after `git lfs pull` bakes the real weights in.
RUN MODEL="runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt"; \
    if [ ! -f "$MODEL" ]; then \
      echo "ERROR: model weights not found: $MODEL"; exit 1; \
    fi; \
    if head -c 64 "$MODEL" | grep -q "git-lfs"; then \
      echo "ERROR: $MODEL is a Git-LFS pointer stub, not the real model."; \
      echo "Run 'git lfs pull' before 'docker build'."; exit 1; \
    fi; \
    echo "Model weights OK ($(wc -c < "$MODEL") bytes)"

EXPOSE 8080

# Production WSGI server. SECRET_KEY must be supplied at runtime or the app
# refuses to start (ATIS_ENV=production). See gunicorn.conf.py for tuning.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
