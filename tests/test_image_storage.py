"""Image storage backend tests."""

import boto3

from models import Inspection, db
from routes import inspections as inspection_routes
from services import image_storage


class FakeS3Client:
    def __init__(self):
        self.deleted = []
        self.puts = []
        self.presigned = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.presigned.append({
            "operation": operation,
            "params": Params,
            "expires": ExpiresIn,
        })
        return f"https://objects.example/{Params['Key']}?expires={ExpiresIn}"


def test_s3_client_uses_retry_and_timeout_config(monkeypatch):
    calls = []

    def fake_client(service_name, **kwargs):
        calls.append((service_name, kwargs))
        return FakeS3Client()

    monkeypatch.setenv("ATIS_S3_CONNECT_TIMEOUT", "4")
    monkeypatch.setenv("ATIS_S3_READ_TIMEOUT", "12")
    monkeypatch.setenv("ATIS_S3_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("ATIS_S3_RETRY_MODE", "adaptive")
    monkeypatch.setattr(boto3, "client", fake_client)

    image_storage._s3_client()

    assert calls[0][0] == "s3"
    config = calls[0][1]["config"]
    assert config.connect_timeout == 4
    assert config.read_timeout == 12
    assert config.retries["max_attempts"] == 5
    assert config.retries["mode"] == "adaptive"


def test_s3_delete_and_signed_url(monkeypatch):
    fake_client = FakeS3Client()

    monkeypatch.setenv("ATIS_S3_BUCKET", "atis-bucket")
    monkeypatch.setenv("ATIS_S3_SIGNED_URLS", "1")
    monkeypatch.setenv("ATIS_S3_SIGNED_URL_EXPIRES", "120")
    monkeypatch.setattr(image_storage, "_s3_client", lambda: fake_client)
    inspection = Inspection(
        location="S3 Gate",
        status="safe",
        confidence=90,
        image_storage="s3",
        image_object_key="inspection-images/test.jpg",
    )

    assert image_storage.delete_image(inspection) is True
    assert image_storage.signed_image_url(inspection) == "https://objects.example/inspection-images/test.jpg?expires=120"
    assert fake_client.deleted == [{
        "Bucket": "atis-bucket",
        "Key": "inspection-images/test.jpg",
    }]
    assert fake_client.presigned == [{
        "operation": "get_object",
        "params": {
            "Bucket": "atis-bucket",
            "Key": "inspection-images/test.jpg",
        },
        "expires": 120,
    }]


def test_media_route_redirects_to_signed_s3_url(auth_client, app, monkeypatch):
    with app.app_context():
        insp = Inspection(
            location="Signed URL Gate",
            status="safe",
            confidence=91,
            image_storage="s3",
            image_object_key="inspection-images/signed.jpg",
            image_mime="image/jpeg",
            image_size=9,
        )
        db.session.add(insp)
        db.session.commit()
        inspection_id = insp.id

    monkeypatch.setattr(
        inspection_routes,
        "signed_image_url",
        lambda inspection: f"https://objects.example/{inspection.image_object_key}",
    )

    resp = auth_client.get(f"/media/inspection/{inspection_id}", follow_redirects=False)

    assert resp.status_code in (302, 303)
    assert resp.headers["Location"] == "https://objects.example/inspection-images/signed.jpg"
