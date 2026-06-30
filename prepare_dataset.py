"""
prepare_dataset.py — Build the ATIS classification dataset.

Pools tire images from one or more sources, normalizes them to two classes
(``normal`` / ``cracked``), drops corrupt files and exact duplicates (by content
hash), and writes a **stratified, leakage-free** train/val/test split in the
Ultralytics classification layout:

    ATIS_Dataset/{train,val,test}/{normal,cracked}/

Each unique image is assigned to exactly one split (deduped globally by SHA-1),
so the same picture can never leak across train/val/test. Validation and test
images are real and never augmented.

Sources always include the local ``Tire Textures/`` set. Add more with --source
(a folder or .zip), repeatable. A Kaggle slug works too if the kaggle CLI and
credentials are available.

Usage:
    python3 prepare_dataset.py
    python3 prepare_dataset.py --source /path/to/extra_dataset
    python3 prepare_dataset.py --source /path/to/dataset.zip
    python3 prepare_dataset.py --source warcoder/tyre-quality-classification --kaggle
"""

import argparse
import hashlib
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Optional perceptual-hash near-duplicate removal. Exact SHA-1 dedup only catches
# byte-identical files; resized/recompressed copies of the SAME tire across public
# datasets slip through and can leak the same image across train/val/test. A
# perceptual hash (pHash) catches those near-duplicates. Degrades gracefully to
# SHA-1-only (with a warning) if imagehash is not installed: pip install imagehash
try:
    import imagehash
except ImportError:  # optional dependency
    imagehash = None

PHASH_MAX_DISTANCE = 5  # Hamming distance <= this between pHashes => same image

BASE_DIR = Path(__file__).resolve().parent
DEST_DIR = BASE_DIR / "ATIS_Dataset"
DEFAULT_SOURCE = BASE_DIR / "Tire Textures"

CLASSES = ("normal", "cracked")
SPLITS = ("train", "val", "test")
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SEED = 0

# Map arbitrary source folder names (lowercased, exact match) to our two classes.
# infer_class() normalises folder names: lowercased, with spaces/hyphens -> "_"
# (so "Flat spots" -> "flat_spots", "Non-defective" -> "non_defective").
# Any folder name NOT listed here is treated as "unclassified" and skipped — this
# is how ambiguous labels are intentionally excluded (see "serviceable" below).
CLASS_ALIASES = {
    # --- normal / safe ---
    "normal": "normal", "good": "normal", "fresh": "normal", "intact": "normal",
    "no_crack": "normal", "non_defective": "normal", "healthy": "normal",
    "new": "normal",                      # workshop set (sameersambhare1): NEW
    # --- cracked / defective (any structural defect maps here for the 2-class model) ---
    "cracked": "cracked", "crack": "cracked", "cracking": "cracked",
    "cracks": "cracked", "defective": "cracked", "damaged": "cracked",
    "bad": "cracked", "defect": "cracked",
    "unusable": "cracked",                # workshop set: UNUSABLE (severe wear/cracks)
    "bulge": "cracked", "bulged": "cracked", "sidewall_bulge": "cracked",
    "nail": "cracked", "nails": "cracked",
    "flat_spot": "cracked", "flat_spots": "cracked", "flatspot": "cracked",
    # Intentionally NOT mapped (excluded as label-noise): "serviceable" (workshop
    # set's middle class). Add `"serviceable": "normal"` here if you decide to keep
    # those as passable tires.
}


def infer_class(path: Path) -> str | None:
    """Infer normal/cracked from the class folder in an image's path (exact match)."""
    for part in reversed(path.parts[:-1]):  # skip the filename itself
        key = part.strip().lower().replace(" ", "_").replace("-", "_")
        if key in CLASS_ALIASES:
            return CLASS_ALIASES[key]
    return None


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def kaggle_download(slug: str) -> Path:
    """Download + unzip a Kaggle dataset into a temp dir. Requires kaggle creds."""
    tmp = Path(tempfile.mkdtemp(prefix="atis_kaggle_"))
    print(f"  Downloading Kaggle dataset '{slug}' -> {tmp}")
    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", slug, "-p", str(tmp), "--unzip"],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"Kaggle download failed ({exc}). Install the kaggle CLI and place an API "
            f"token at ~/.kaggle/kaggle.json, or download the dataset manually and pass "
            f"its folder/zip path with --source."
        )
    return tmp


def resolve_source(source: str, is_kaggle: bool) -> tuple[Path, bool]:
    """Return (root_path, is_temp) for a source given as a folder, .zip, or kaggle slug."""
    if is_kaggle:
        return kaggle_download(source), True

    path = Path(source).expanduser()
    if not path.exists():
        raise SystemExit(f"Source not found: {path}")
    if path.is_file() and path.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="atis_zip_"))
        print(f"  Extracting {path.name} -> {tmp}")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        return tmp, True
    return path, False


def collect_images(roots: list[Path]) -> tuple[dict[str, list[Path]], dict[str, int]]:
    """Walk sources, assign classes, drop corrupt files and global duplicates.

    Returns ({class: [paths]}, stats).
    """
    by_class: dict[str, list[Path]] = defaultdict(list)
    seen_hashes: set[str] = set()
    seen_phashes: list = []  # imagehash.ImageHash objects of kept images
    stats = {
        "scanned": 0, "unclassified": 0, "corrupt": 0,
        "duplicate": 0, "near_duplicate": 0, "kept": 0,
    }

    if imagehash is None:
        print(
            "  [warn] imagehash not installed -> exact (SHA-1) dedup only; "
            "near-duplicate copies across datasets won't be caught. "
            "Install with: pip install imagehash"
        )

    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            stats["scanned"] += 1

            cls = infer_class(path)
            if cls is None:
                stats["unclassified"] += 1
                continue

            try:
                with Image.open(path) as img:
                    img.verify()
            except (UnidentifiedImageError, OSError):
                stats["corrupt"] += 1
                continue

            digest = file_hash(path)
            if digest in seen_hashes:
                stats["duplicate"] += 1
                continue

            # Perceptual near-duplicate check (re-open: verify() consumes the file).
            phash = None
            if imagehash is not None:
                try:
                    with Image.open(path) as img:
                        phash = imagehash.phash(img.convert("RGB"))
                except (UnidentifiedImageError, OSError):
                    stats["corrupt"] += 1
                    continue
                if any((phash - seen) <= PHASH_MAX_DISTANCE for seen in seen_phashes):
                    stats["near_duplicate"] += 1
                    continue

            seen_hashes.add(digest)
            if phash is not None:
                seen_phashes.append(phash)
            by_class[cls].append(path)
            stats["kept"] += 1

    return by_class, stats


def split_class(paths: list[Path], rng: random.Random) -> dict[str, list[Path]]:
    """Stratified split of one class's images into train/val/test."""
    shuffled = paths[:]
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * SPLIT_RATIOS["train"])
    n_val = int(n * SPLIT_RATIOS["val"])
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train:n_train + n_val],
        "test": shuffled[n_train + n_val:],
    }


def build_dataset(sources: list[tuple[str, bool]]) -> None:
    roots = [DEFAULT_SOURCE]
    temp_dirs: list[Path] = []
    for source, is_kaggle in sources:
        root, is_temp = resolve_source(source, is_kaggle)
        roots.append(root)
        if is_temp:
            temp_dirs.append(root)

    print("Collecting images from:")
    for r in roots:
        print(f"  - {r}")
    by_class, stats = collect_images(roots)

    if not all(by_class.get(c) for c in CLASSES):
        raise SystemExit(f"Missing images for a class. Found: { {c: len(by_class.get(c, [])) for c in CLASSES} }")

    print(
        f"\nScanned {stats['scanned']} images | kept {stats['kept']} "
        f"| skipped: {stats['unclassified']} unclassified, "
        f"{stats['corrupt']} corrupt, {stats['duplicate']} duplicates, "
        f"{stats['near_duplicate']} near-duplicates"
    )

    # Fresh destination so re-runs are reproducible.
    if DEST_DIR.exists():
        shutil.rmtree(DEST_DIR)

    rng = random.Random(SEED)
    counts: dict[str, dict[str, int]] = {s: {} for s in SPLITS}
    placed_hashes: dict[str, str] = {}  # hash -> split, to verify no leakage

    for cls in CLASSES:
        split_map = split_class(by_class[cls], rng)
        for split, items in split_map.items():
            out_dir = DEST_DIR / split / cls
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in items:
                digest = file_hash(src)
                dst = out_dir / f"{digest}{src.suffix.lower()}"
                shutil.copy2(src, dst)
                if digest in placed_hashes and placed_hashes[digest] != split:
                    raise SystemExit(f"LEAKAGE: {digest} in {placed_hashes[digest]} and {split}")
                placed_hashes[digest] = split
            counts[split][cls] = len(items)

    # Report
    print(f"\nDataset written to {DEST_DIR}")
    header = f"{'split':<7} " + " ".join(f"{c:>9}" for c in CLASSES) + f"{'total':>9}"
    print(header)
    print("-" * len(header))
    for split in SPLITS:
        row = counts[split]
        total = sum(row.values())
        print(f"{split:<7} " + " ".join(f"{row[c]:>9}" for c in CLASSES) + f"{total:>9}")
    grand = sum(sum(counts[s].values()) for s in SPLITS)
    print("-" * len(header))
    print(f"{'TOTAL':<7} " + " ".join(f"{sum(counts[s][c] for s in SPLITS):>9}" for c in CLASSES) + f"{grand:>9}")
    print("\nNo hash appears in more than one split (leakage check passed).")

    for tmp in temp_dirs:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ATIS classification dataset.")
    parser.add_argument(
        "--source", action="append", default=[],
        help="Extra dataset folder, .zip, or (with --kaggle) a Kaggle slug. Repeatable.",
    )
    parser.add_argument(
        "--kaggle", action="store_true",
        help="Treat each --source as a Kaggle dataset slug to download.",
    )
    args = parser.parse_args()

    sources = [(s, args.kaggle) for s in args.source]
    build_dataset(sources)
    print("\nDataset restructuring complete. Ready for YOLO training.")


if __name__ == "__main__":
    main()
