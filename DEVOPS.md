# ATIS Development Workflow

This document explains how to work safely in the ATIS GitHub repository while the project is built step by step with AI prompts.

ATIS is a Flask-based final-year project. Keep the repo Flask-based unless the product requirements are intentionally changed.

## 1. Branching Strategy

- `main` is the stable final/demo branch only.
- `dev` is the active integration branch.
- Feature branches are created from `dev`.
- Feature branches are merged back into `dev` after testing.
- `dev` is merged into `main` only after a stable milestone.

Do not commit directly to `main`.

## 2. Feature Branches

Use these branches for the planned build sequence:

- `setup/project-structure`
- `feature/database-models`
- `feature/auth`
- `feature/base-ui`
- `feature/dashboard`
- `feature/inspection-upload`
- `feature/ai-preprocessing`
- `feature/mock-classifier`
- `feature/inspection-analysis`
- `feature/alerts-history-reports`
- `feature/real-model-integration`
- `release/v1-demo`

## 3. Prompt-to-Branch Mapping

| Prompt | Branch |
|---|---|
| Prompts 1-4 | `setup/project-structure` |
| Prompt 5 | `feature/database-models` |
| Prompt 6 | `feature/auth` |
| Prompt 7 | `feature/base-ui` |
| Prompt 8 | `feature/dashboard` |
| Prompt 9 | `feature/inspection-upload` |
| Prompt 10 | `feature/ai-preprocessing` |
| Prompt 11 | `feature/mock-classifier` |
| Prompt 12 | `feature/inspection-analysis` |
| Prompts 13-16 | `feature/alerts-history-reports` |
| Prompt 17 | `feature/real-model-integration` |
| Prompt 18 | `release/v1-demo` |

## 4. Milestones

| Version | Goal |
|---|---|
| `v0.1` | Flask app runs |
| `v0.2` | Authentication works |
| `v0.3` | Dashboard works |
| `v0.4` | Upload works |
| `v0.5` | Mock AI analysis works |
| `v0.6` | Alerts, history, and reports work |
| `v1.0` | Final demo version |

## 5. Before-Push Checklist

Before every push, check:

- Correct branch is active.
- Flask app runs locally.
- Imports are correct.
- Database migrations are checked.
- No secrets are committed.
- No uploaded images are committed.
- No model files are committed.
- No cache files are committed.
- No virtual environments are committed.
- No database files are committed.
- Commit message is clear.

Useful checks:

```bash
git branch --show-current
git status --short
```

## 6. Merge Rules

- Never commit directly to `main`.
- Merge feature branches into `dev` only after testing.
- Merge `dev` into `main` only after a stable milestone.
- Tag stable versions after merging into `main`.
- Keep commit messages short and clear.

## 7. Commit Message Examples

- `Add Flask app factory`
- `Create database models`
- `Implement login and logout`
- `Add tire image upload`
- `Create mock classifier service`
- `Build alerts page`
- `Fix inspection detail route`

## 8. Git Command Examples

### Create `dev`

```bash
git switch main
git pull origin main
git switch -c dev
git push -u origin dev
```

### Create a Feature Branch

```bash
git switch dev
git pull origin dev
git switch -c feature/database-models
```

### Commit Changes

```bash
git status --short
git add .
git commit -m "Create database models"
```

### Push Branch

```bash
git push -u origin feature/database-models
```

### Merge Feature Branch Into `dev`

```bash
git switch dev
git pull origin dev
git merge feature/database-models
git push origin dev
```

### Delete a Merged Feature Branch

```bash
git branch -d feature/database-models
git push origin --delete feature/database-models
```

### Merge `dev` Into `main`

```bash
git switch main
git pull origin main
git merge dev
git push origin main
```

### Tag Versions

```bash
git switch main
git pull origin main
git tag v0.1
git push origin v0.1
```

For later milestones, replace `v0.1` with the correct version tag, such as `v0.2`, `v0.3`, or `v1.0`.

## 9. Upload Safety Rules

Do not commit:

- `.env` files
- Local SQLite database files
- Files inside `instance/`
- Uploaded inspection images
- Exported reports
- Trained model files such as `.h5`, `.keras`, `.pt`, `.pth`, or `.onnx`
- Cache folders such as `__pycache__/` and `.pytest_cache/`
- Virtual environments
- IDE settings

If a large file is needed for the final demo, document where to place it locally instead of committing it to Git.
