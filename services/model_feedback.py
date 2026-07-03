"""Model-feedback dataset export helpers."""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from services.image_storage import load_image


def _extension_for_mime(mime: str | None) -> str:
    normalized = (mime or "").split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }.get(normalized, ".jpg")


def _safe_label(label: str | None) -> str:
    value = (label or "unlabeled").strip().lower().replace(" ", "_")
    return "".join(ch for ch in value if ch.isalnum() or ch in {"_", "-"}) or "unlabeled"


def build_feedback_dataset_zip(inspections) -> tuple[BytesIO, dict[str, int]]:
    """Build a corrected-image dataset ZIP from reviewed inspections.

    The archive contains:
    - `manifest.csv` with review/model metadata for every included image
    - `images/<correction_label>/inspection_<id>.<ext>` image files
    """
    buffer = BytesIO()
    manifest = StringIO()
    writer = csv.writer(manifest)
    writer.writerow([
        "inspection_id",
        "image_path",
        "label",
        "review_status",
        "reviewer_email",
        "reviewed_at",
        "predicted_class",
        "status",
        "confidence",
        "model_version",
        "model_threshold",
        "inference_ms",
        "plate",
        "location",
        "camera",
        "defects",
    ])

    included = 0
    skipped_missing_image = 0
    label_counts: dict[str, int] = {}

    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for inspection in inspections:
            image_bytes, image_mime = load_image(inspection)
            if not image_bytes:
                skipped_missing_image += 1
                continue

            label = _safe_label(inspection.correction_label)
            label_counts[label] = label_counts.get(label, 0) + 1
            image_name = f"images/{label}/inspection_{inspection.id}{_extension_for_mime(image_mime)}"
            archive.writestr(image_name, image_bytes)
            writer.writerow([
                inspection.id,
                image_name,
                label,
                inspection.review_status,
                inspection.reviewer.email if inspection.reviewer else "",
                inspection.reviewed_at.isoformat() if inspection.reviewed_at else "",
                inspection.predicted_class or "",
                inspection.status,
                inspection.confidence,
                inspection.model_version or "",
                inspection.model_threshold if inspection.model_threshold is not None else "",
                inspection.inference_ms if inspection.inference_ms is not None else "",
                inspection.plate or "",
                inspection.location or "",
                inspection.camera or "",
                "; ".join(inspection.defect_list),
            ])
            included += 1

        archive.writestr("manifest.csv", manifest.getvalue().encode("utf-8-sig"))
        archive.writestr(
            "README.txt",
            (
                "ATIS model-feedback export\n"
                "\n"
                "Images are grouped by human correction label under images/<label>/.\n"
                "Use manifest.csv for metadata, model version, review status, and traceability.\n"
                "Only reviewed inspections with correction_label and available image bytes are included.\n"
            ),
        )

    buffer.seek(0)
    return buffer, {
        "included": included,
        "skipped_missing_image": skipped_missing_image,
        "label_count": len(label_counts),
    }


def default_feedback_filename(date_from: str, date_to: str) -> str:
    return f"ATIS_model_feedback_{date_from}_to_{date_to}.zip"
