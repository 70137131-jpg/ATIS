"""S3 image-storage backend integration tests (mocked with moto).

Exercises the real ``ATIS_IMAGE_STORAGE=s3`` code path — put, get, presigned
URL, delete — against an in-memory S3 provided by moto, so the object-storage
backend is covered without a live bucket.
"""

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from services import image_storage  # noqa: E402

BUCKET = "atis-test-bucket"


@pytest.fixture()
def s3_env(monkeypatch):
    monkeypatch.setenv("ATIS_IMAGE_STORAGE", "s3")
    monkeypatch.setenv("ATIS_S3_BUCKET", BUCKET)
    monkeypatch.setenv("ATIS_S3_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


class _FakeInspection:
    """Minimal stand-in carrying the image-storage columns load/delete read."""
    def __init__(self, stored):
        self.image_storage = stored.storage
        self.image_object_key = stored.object_key
        self.image_mime = stored.mime
        self.image_data = stored.data


def test_store_and_load_roundtrip(s3_env):
    data = b"\xff\xd8\xff\xe0jpeg-bytes"
    stored = image_storage.store_image(data, filename="tyre.jpg", mime="image/jpeg")
    assert stored.storage == "s3"
    assert stored.object_key.endswith("tyre.jpg")
    assert stored.data is None  # bytes live in S3, not the row

    loaded, mime = image_storage.load_image(_FakeInspection(stored))
    assert loaded == data
    assert mime == "image/jpeg"


def test_presigned_url_when_enabled(s3_env, monkeypatch):
    monkeypatch.setenv("ATIS_S3_SIGNED_URLS", "1")
    stored = image_storage.store_image(b"abc", filename="x.jpg", mime="image/jpeg")
    url = image_storage.signed_image_url(_FakeInspection(stored))
    assert url and url.startswith("https://")
    assert BUCKET in url


def test_presigned_url_none_when_disabled(s3_env, monkeypatch):
    monkeypatch.setenv("ATIS_S3_SIGNED_URLS", "0")
    stored = image_storage.store_image(b"abc", filename="x.jpg", mime="image/jpeg")
    assert image_storage.signed_image_url(_FakeInspection(stored)) is None


def test_delete_removes_object(s3_env):
    stored = image_storage.store_image(b"abc", filename="del.jpg", mime="image/jpeg")
    insp = _FakeInspection(stored)
    assert image_storage.delete_image(insp) is True
    # After deletion the object is gone -> load raises a client error.
    with pytest.raises(Exception):
        image_storage.load_image(insp)


def test_missing_bucket_env_is_rejected(monkeypatch):
    monkeypatch.setenv("ATIS_IMAGE_STORAGE", "s3")
    monkeypatch.delenv("ATIS_S3_BUCKET", raising=False)
    with mock_aws():
        with pytest.raises(RuntimeError):
            image_storage.store_image(b"abc", filename="x.jpg", mime="image/jpeg")
