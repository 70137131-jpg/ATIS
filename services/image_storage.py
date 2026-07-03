"""Inspection image storage backends.

The default backend stores bytes in the inspections table for demos and tests.
Production can use S3-compatible object storage by setting ATIS_IMAGE_STORAGE=s3
plus the usual bucket/credential environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredImage:
    storage: str
    mime: str
    size: int
    object_key: str | None = None
    data: bytes | None = None


def configured_backend() -> str:
    return os.environ.get("ATIS_IMAGE_STORAGE", "db").strip().lower() or "db"


def signed_urls_enabled() -> bool:
    raw = os.environ.get("ATIS_S3_SIGNED_URLS", "0")
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def object_key_for(filename: str) -> str:
    prefix = os.environ.get("ATIS_IMAGE_PREFIX", "inspection-images").strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def store_image(image_bytes: bytes, *, filename: str, mime: str) -> StoredImage:
    """Persist image bytes using the configured backend."""
    backend = configured_backend()
    if backend in {"db", "database"}:
        return StoredImage(storage="db", mime=mime, size=len(image_bytes), data=image_bytes)
    if backend == "s3":
        key = object_key_for(filename)
        _s3_client().put_object(
            Bucket=_required_env("ATIS_S3_BUCKET"),
            Key=key,
            Body=image_bytes,
            ContentType=mime,
        )
        return StoredImage(storage="s3", mime=mime, size=len(image_bytes), object_key=key)
    raise RuntimeError(f"Unsupported ATIS_IMAGE_STORAGE backend: {backend}")


def load_image(inspection) -> tuple[bytes | None, str | None]:
    """Return image bytes and MIME type for an inspection, or (None, None)."""
    storage = (inspection.image_storage or "").lower()
    if storage == "s3" and inspection.image_object_key:
        obj = _s3_client().get_object(
            Bucket=_required_env("ATIS_S3_BUCKET"),
            Key=inspection.image_object_key,
        )
        return obj["Body"].read(), inspection.image_mime or obj.get("ContentType")

    if inspection.image_data:
        return inspection.image_data, inspection.image_mime
    return None, None


def delete_image(inspection) -> bool:
    """Delete an inspection image from its external backend when applicable."""
    storage = (inspection.image_storage or "").lower()
    if storage == "s3" and inspection.image_object_key:
        _s3_client().delete_object(
            Bucket=_required_env("ATIS_S3_BUCKET"),
            Key=inspection.image_object_key,
        )
        return True
    return False


def signed_image_url(inspection, *, expires_seconds: int | None = None) -> str | None:
    """Return a temporary direct object URL when signed S3 URLs are enabled."""
    storage = (inspection.image_storage or "").lower()
    if storage != "s3" or not inspection.image_object_key or not signed_urls_enabled():
        return None

    expires = expires_seconds or int(os.environ.get("ATIS_S3_SIGNED_URL_EXPIRES", "900"))
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": _required_env("ATIS_S3_BUCKET"),
            "Key": inspection.image_object_key,
        },
        ExpiresIn=expires,
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set when ATIS_IMAGE_STORAGE=s3")
    return value


def _s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "boto3 and botocore must be installed when ATIS_IMAGE_STORAGE=s3"
        ) from exc

    kwargs = {}
    endpoint_url = os.environ.get("ATIS_S3_ENDPOINT_URL")
    region_name = os.environ.get("ATIS_S3_REGION")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if region_name:
        kwargs["region_name"] = region_name
    kwargs["config"] = Config(
        connect_timeout=float(os.environ.get("ATIS_S3_CONNECT_TIMEOUT", "3")),
        read_timeout=float(os.environ.get("ATIS_S3_READ_TIMEOUT", "10")),
        retries={
            "max_attempts": int(os.environ.get("ATIS_S3_MAX_ATTEMPTS", "3")),
            "mode": os.environ.get("ATIS_S3_RETRY_MODE", "standard"),
        },
    )
    return boto3.client("s3", **kwargs)
