import json

from minio.error import S3Error

from openzetc.storage.minio.client import MinIOClient, normalize_public_minio_url


class FakeMinio:
    def __init__(self):
        self.policy = None
        self.put_calls = 0

    def bucket_exists(self, bucket_name: str) -> bool:
        return False

    def make_bucket(self, bucket_name: str) -> None:
        return None

    def set_bucket_policy(self, bucket_name: str, policy: str) -> None:
        self.policy = json.loads(policy)

    def put_object(self, **kwargs):
        self.put_calls += 1
        return object()


def _access_denied() -> S3Error:
    return S3Error(None, "AccessDenied", "denied", "/", "request", "host")


class RestrictedBucketCheckMinio(FakeMinio):
    def bucket_exists(self, bucket_name: str) -> bool:
        raise _access_denied()


class RestrictedPolicyMinio(FakeMinio):
    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def set_bucket_policy(self, bucket_name: str, policy: str) -> None:
        raise _access_denied()


def test_public_image_uses_same_origin_url_without_bucket_listing(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")
    client = MinIOClient()
    fake_minio = FakeMinio()
    client._client = fake_minio

    result = client.upload_file("public", "images/user 1/avatar.png", b"image", "image/png")

    assert result.url == "/minio/public/images/user%201/avatar.png"
    assert fake_minio.policy is not None
    actions = [action for statement in fake_minio.policy["Statement"] for action in statement["Action"]]
    assert actions == ["s3:GetObject"]


def test_legacy_public_minio_url_is_normalized_to_same_origin(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")

    assert (
        normalize_public_minio_url("http://example.test:9000/public/avatar/user.png") == "/minio/public/avatar/user.png"
    )
    assert normalize_public_minio_url("https://cdn.example.test/public/user.png") == (
        "https://cdn.example.test/public/user.png"
    )


def test_legacy_public_minio_url_preserves_query_and_fragment(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")

    assert (
        normalize_public_minio_url("http://example.test:9000/public/avatar/user.png?v=123#preview")
        == "/minio/public/avatar/user.png?v=123#preview"
    )


def test_upload_continues_when_scoped_credentials_cannot_check_bucket(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")
    client = MinIOClient()
    fake_minio = RestrictedBucketCheckMinio()
    client._client = fake_minio

    result = client.upload_file("public", "images/avatar.png", b"image", "image/png")

    assert result.url == "/minio/public/images/avatar.png"
    assert fake_minio.put_calls == 1


def test_upload_continues_when_bucket_policy_is_managed_externally(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")
    client = MinIOClient()
    fake_minio = RestrictedPolicyMinio()
    client._client = fake_minio

    result = client.upload_file("public", "images/avatar.png", b"image", "image/png")

    assert result.url == "/minio/public/images/avatar.png"
    assert fake_minio.put_calls == 1
