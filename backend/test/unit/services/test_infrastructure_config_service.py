from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from yuxi.services import infrastructure_config_service as service

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_object_storage_connection_test_uses_draft_settings(monkeypatch):
    seen = {}

    class FakeBucketsClient:
        def bucket_exists(self, bucket_name):
            seen.setdefault("buckets", []).append(bucket_name)
            return True

    class FakeObjectStorage:
        def __init__(self, settings):
            seen["settings"] = settings
            self.client = FakeBucketsClient()

    monkeypatch.setattr(service, "MinIOClient", FakeObjectStorage)

    result = await service.test_infrastructure_connection(
        "object_storage",
        {
            "provider": "s3_compatible",
            "endpoint": "https://s3.example.com",
            "access_key": "access",
            "secret_key": "secret",
            "documents_bucket": "documents",
            "public_bucket": "public",
        },
    )

    assert result["status"] == "ok"
    assert set(seen["buckets"]) == {"documents", "public"}
    assert seen["settings"]["endpoint"] == "https://s3.example.com"


async def test_vector_and_graph_connection_tests_dispatch_to_protocol_clients(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_test_milvus", lambda settings: calls.append(("vector", settings["uri"])))
    monkeypatch.setattr(service, "_test_neo4j", lambda settings: calls.append(("graph", settings["uri"])))

    await service.test_infrastructure_connection(
        "vector_database",
        {
            "provider": "zilliz",
            "uri": "https://vector.example.com",
            "name": "default",
            "token": "test-token",
        },
    )
    await service.test_infrastructure_connection(
        "graph_database",
        {
            "provider": "neo4j_aura",
            "uri": "neo4j+s://graph.example.com",
            "username": "neo4j",
            "password": "secret",
            "name": "neo4j",
        },
    )

    assert calls == [
        ("vector", "https://vector.example.com"),
        ("graph", "neo4j+s://graph.example.com"),
    ]


async def test_connection_test_rejects_missing_required_values():
    with pytest.raises(ValueError, match="缺少必填配置"):
        await service.test_infrastructure_connection(
            "graph_database",
            {"provider": "neo4j", "uri": "bolt://graph:7687", "username": "neo4j", "password": ""},
        )


async def test_object_storage_connection_rejects_missing_bucket(monkeypatch):
    class FakeBucketsClient:
        def bucket_exists(self, bucket_name):
            return bucket_name == "documents"

    class FakeObjectStorage:
        def __init__(self, _settings):
            self.client = FakeBucketsClient()

    monkeypatch.setattr(service, "MinIOClient", FakeObjectStorage)

    with pytest.raises(ValueError, match="Bucket 不存在: public"):
        await service.test_infrastructure_connection(
            "object_storage",
            {
                "provider": "minio",
                "endpoint": "http://minio:9000",
                "access_key": "access",
                "secret_key": "secret",
                "documents_bucket": "documents",
                "public_bucket": "public",
            },
        )


async def test_milvus_connection_rejects_missing_database(monkeypatch):
    monkeypatch.setattr(service.connections, "connect", lambda **_kwargs: None)
    monkeypatch.setattr(service.connections, "has_connection", lambda _alias: True)
    monkeypatch.setattr(service.connections, "disconnect", lambda _alias: None)
    monkeypatch.setattr(service.db, "list_database", lambda **_kwargs: ["default"])

    with pytest.raises(ValueError, match="向量数据库不存在: knowledge"):
        service._test_milvus({"uri": "http://milvus:19530", "token": "", "name": "knowledge"})


async def test_managed_vector_database_requires_token():
    with pytest.raises(ValueError, match="缺少必填配置: token"):
        await service.test_infrastructure_connection(
            "vector_database",
            {"provider": "zilliz", "uri": "https://vector.example.com", "name": "default", "token": ""},
        )


async def test_reveal_infrastructure_secret_only_allows_secret_fields(monkeypatch):
    class FakeRow:
        config_json = {"secret_key": "stored-secret"}

    class FakeRepository:
        def __init__(self, _session):
            pass

        async def get_active(self, section):
            return FakeRow() if section == "object_storage" else None

    @asynccontextmanager
    async def fake_session_context():
        yield object()

    monkeypatch.setattr(service, "InfrastructureConfigRepository", FakeRepository)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", fake_session_context)

    assert await service.reveal_infrastructure_secret("object_storage", "secret_key") == {
        "section": "object_storage",
        "field": "secret_key",
        "value": "stored-secret",
    }

    with pytest.raises(ValueError, match="不支持查看"):
        await service.reveal_infrastructure_secret("object_storage", "access_key")


async def test_database_secret_values_are_encrypted_and_round_trip(monkeypatch):
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "unit-test-stable-key")
    values = {"provider": "minio", "secret_key": "stored-secret"}

    encrypted = service._encrypt_database_values("object_storage", values)

    assert encrypted["secret_key"].startswith(service.ENCRYPTED_VALUE_PREFIX)
    assert "stored-secret" not in encrypted["secret_key"]
    assert service._decrypt_database_values("object_storage", encrypted) == values


async def test_local_minio_uses_deployment_account_and_password(monkeypatch):
    monkeypatch.setenv("MINIO_ACCESS_KEY", "local-account")
    monkeypatch.setenv("MINIO_SECRET_KEY", "local-password")

    resolved = service._resolve_infrastructure_values(
        "object_storage",
        {
            "provider": "minio",
            "endpoint": "http://minio:9000",
            "access_key": "",
            "secret_key": service.SYSTEM_DEFAULT_SECRET,
        },
    )

    assert resolved["access_key"] == "local-account"
    assert resolved["secret_key"] == "local-password"
    masked = service._local_minio_defaults(masked=True)
    assert masked["access_key"] == "local-account"
    assert masked["secret_key"] == "********"


async def test_source_draft_mask_keeps_that_sources_secret():
    resolved = service._resolve_infrastructure_values(
        "graph_database",
        {
            "provider": "neo4j_aura",
            "uri": "neo4j+s://new.example.com",
            "username": "neo4j",
            "password": "********",
            "name": "neo4j",
        },
        base_values={
            "provider": "neo4j_aura",
            "uri": "neo4j+s://old.example.com",
            "username": "neo4j",
            "password": "source-specific-password",
            "name": "neo4j",
            "console_url": "",
        },
    )

    assert resolved["uri"] == "neo4j+s://new.example.com"
    assert resolved["password"] == "source-specific-password"
