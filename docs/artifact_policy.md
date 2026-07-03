# ATIS Data and Artifact Policy

This repo keeps source code, migrations, tests, configuration examples, docs,
and small runtime model artifacts needed to build and demo the app. It should
not become storage for raw datasets, generated training workspaces, or ad hoc
experiment outputs.

## Keep in Git

- Application source, templates, static assets, migrations, and tests.
- Model metadata that explains a shipped model, including `model_card.json`,
  calibration notes, and evaluation summaries.
- Small runtime weights required by the current Docker/app path, stored through
  Git LFS:
  - `runs/classify/runs/classify/ATIS_Project/tyre_safety_model/weights/best.pt`
  - `yolo26n.pt` while the optional object-gate path uses it.

## Keep in Git LFS

Git LFS is appropriate for model or visual artifacts that are required by the
checked-in app and are small enough for normal clone/build workflows:

- `*.pt`, `*.pth`, `*.onnx`, `*.engine`
- committed `*.png`, `*.jpg`, and `*.jpeg` evaluation/demo images

Do not use Git LFS as a dumping ground for every experiment. A model artifact
belongs in LFS only when the app, tests, or docs intentionally reference it.

## Keep Outside the Repo

Use external artifact storage for anything large, reproducible, private, or
experiment-specific:

- `ATIS_Dataset/`
- `ATIS_Dataset.zip`
- raw Kaggle/Roboflow/vendor dataset exports
- generated training run directories
- scratch checkpoints such as `last.pt`, `epoch*.pt`, and `*.bak.pt`
- exported reports or uploaded inspection images

Recommended locations are S3-compatible object storage, Hugging Face datasets,
Kaggle datasets, or a managed artifact registry. Record the source, version,
checksum, license, and restore command in docs before relying on an external
artifact for training or deployment.

## Current Decision

The production/demo classifier is the trained `best.pt` artifact documented by
the model card. Keep that file in Git LFS because the Docker build and local app
need it.

The local `ATIS_Dataset.zip` file is a 3.5 GB dataset archive and must remain
untracked. Recreate it from the data sources and steps in `DATA_HANDOFF.md`, or
publish it to external artifact storage with a checksum if another environment
needs the exact archive.
