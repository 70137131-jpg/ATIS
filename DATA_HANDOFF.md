# ATIS — Data Expansion Handoff

Self-contained context for a fresh Claude Code session. Goal: grow the tire
dataset toward a production-grade classifier. Written 2026-06-29.

## Project
- **ATIS** (Automated Tire Inspection System) for Pakistan's NHA: a YOLOv11-nano
  **classifier** (`normal` vs `cracked`, image-level — no bounding boxes) + a Flask
  operator dashboard. Repo: `/Users/alihaiderjaffery/Desktop/ATIS` (git).
- ML pipeline files: `prepare_dataset.py` (builds the dataset), `train_model.py`
  (local train) / `colab_train.ipynb` (GPU train on Colab), `evaluate_model.py`
  (test metrics + threshold tuning), `atis_inference.py` (shared inference).
- Inference uses an **asymmetric fail-safe threshold** (`ATIS_CONF_THRESHOLD`,
  default 0.60): a tire passes as "safe" only if predicted `normal` AND confidence
  ≥ threshold; any `cracked` or low-confidence `normal` → unsafe / manual review.

## Current dataset state
`ATIS_Dataset/` holds **1,973 images** (Ultralytics classification layout
`{train,val,test}/{normal,cracked}/`), freshly re-prepped (70/15/15, SHA-1 deduped,
leakage-checked):

| split | cracked | normal | total |
|-------|--------:|-------:|------:|
| train | 705 | 675 | **1,380** |
| val   | 151 | 144 | 295 |
| test  | 152 | 146 | 298 |

- Files are named by SHA-1, so the original source is unrecoverable from filenames.
- **Provenance:** local `Tire Textures/` (1,028 imgs) **is** the Kaggle
  `jehanbhathena/tire-texture-image-recognition` set. The extra ~945 imgs came from
  a 2nd Kaggle source already merged — almost certainly
  `warcoder/tyre-quality-classification` (it's the example in `prepare_dataset.py`).
  This 2nd source is **NOT on disk as a folder** (only its images, renamed by hash,
  live inside `ATIS_Dataset/`).

## Assessment given to the user
- **Enough for an FYP demo, NOT for production.** Last eval ~83% top-1 accuracy and
  ~31% of good tires false-flagged as cracked. Root cause is narrow distribution
  (clean, well-lit studio/web photos), not just raw count. Need more **varied
  real-world** data (real trucks/dirt/wear, real cameras, day+night), target a few
  thousand per class.
- **Night/low-light: it won't work reliably as built, and NO public tire-specific
  night dataset exists.** Only routes: (a) controlled checkpoint lighting (flood/IR)
  — most reliable; (b) self-collected night images; optionally (c) low-light/noise/
  blur augmentation as a software mitigation. Scene-level night driving datasets
  (BDD100K, nuScenes) don't have usable per-tire labels.

## Changes made this session (already in the working tree, uncommitted)
- `prepare_dataset.py`:
  - Expanded `CLASS_ALIASES`: `new`→normal; `unusable`/`bulge`/`nail`/`flat_spot`/
    `flat_spots`→cracked. `serviceable` **intentionally excluded** (label-noise) —
    add `"serviceable": "normal"` if you decide to keep those.
  - Added optional **pHash near-duplicate dedup** (`imagehash`, Hamming dist ≤ 5)
    on top of the existing exact SHA-1 dedup. Degrades gracefully (SHA-1 only, with
    a warning) if `imagehash` is missing. New stat: `near_duplicate`.
    (Validated non-destructively on `Tire Textures/`: caught 1 exact + 11 near dups.)
- `requirements.txt`: added `imagehash>=4.3`.
- Installed locally: `imagehash` 4.3.2 and `kaggle` CLI 2.2.3 (python.org Python
  3.13, global site-packages; pip is NOT externally-managed here).

## ⚠️ Gotchas the next session MUST respect
1. **`prepare_dataset.py` is destructive:** it `shutil.rmtree`s `ATIS_Dataset/` and
   rebuilds from scratch on every run, auto-including only the local `Tire Textures/`
   folder. Running it without re-supplying the warcoder source will **lose the ~945
   warcoder images** (shrink back to ~1,000). Always re-pass every source you want.
2. **`--kaggle` is a global flag** (`main()` applies it to all `--source`). You can't
   mix Kaggle slugs and local folders in one run. Simplest fix: download Kaggle sets
   to local folders first, then run with all sources as **local** `--source` (no
   `--kaggle`).
3. **Roboflow defect datasets are object-detection exports** (boxes, not class
   folders) and mostly contain only defective images (no clean negatives). They do
   NOT drop into the folder-based classifier via `infer_class()`. Defer them to the
   future localization path (the unused `yolo26n.pt` detector), or convert manually.

## Prerequisites the user must provide
- Kaggle API token at `~/.kaggle/kaggle.json` (Kaggle → Account → Create New API
  Token). Without it, no Kaggle downloads.
- (Optional) free Roboflow account + API key, only if pursuing the detection sets.

## Recommended next steps / runbook
Best near-term win: add the real-world workshop set while preserving current data.

```bash
cd "/Users/alihaiderjaffery/Desktop/ATIS"
mkdir -p ~/atis_sources

# 1) re-grab the already-merged set so the rebuild doesn't drop it
python3 -m kaggle datasets download -d warcoder/tyre-quality-classification \
  -p ~/atis_sources/warcoder --unzip
# 2) the new real-world set (closest to checkpoint conditions)
python3 -m kaggle datasets download -d sameersambhare1/tyre-condition-classification-dataset \
  -p ~/atis_sources/workshop --unzip

# 3) rebuild from ALL local sources (Tire Textures auto-included); NOTE: no --kaggle
python3 prepare_dataset.py \
  --source ~/atis_sources/warcoder \
  --source ~/atis_sources/workshop
```
Then: confirm the printed per-split counts rose well past 1,380, confirm the
"no hash appears in more than one split" leakage check passes, re-zip
(`zip -rq ATIS_Dataset.zip ATIS_Dataset -x 'ATIS_Dataset/*.cache'`), retrain via
`colab_train.ipynb`, and run `python3 evaluate_model.py` to compare test recall /
false-positive rate against the current baseline.

## Open offer (not yet done)
Optionally enhance `prepare_dataset.py` to accept per-source Kaggle slugs (e.g. a
`kaggle:slug` prefix) so Kaggle + local sources can be mixed in one command,
removing the manual pre-download step. User has not decided yet.

## Other dataset candidates found (reference)
- Kaggle: `sameersambhare1/tyre-condition-classification-dataset` (real workshop,
  NEW/SERVICEABLE/UNUSABLE — **recommended**), `warcoder/tyre-quality-classification`
  (already merged), `jehanbhathena/tire-texture-image-recognition` (= Tire Textures).
- Roboflow Universe (detection; defer): `adtronics-pmfgf/tire-crack-detection-4z5ei`
  (651; crack/nail/bulge), `yolo-3tbbw/tyre-defect-detection-mmzzm`
  (Bulge/Cracks/Flat spots/Non-defective), `test-i6bsm/tire-crack-detection` (415),
  `yolov8-kvopy/tire-defect-detection-2` (309).
- Industrial/academic tire datasets are X-ray (wrong modality) — skip.
