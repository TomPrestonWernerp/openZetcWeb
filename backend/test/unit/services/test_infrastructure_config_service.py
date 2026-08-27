from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from openzetc.services import infrastructure_config_service as service

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


async def test_migrated_database_secret_with_another_key_is_reported_without_breaking_list(
    monkeypatch,
):
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "source-deployment-key")
    stored = service._encrypt_database_values(
        "object_storage",
        {
            "provider": "aliyun_oss",
            "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
            "access_key": "access",
            "secret_key": "source-secret",
            "region": "cn-hangzhou",
            "documents_bucket": "documents",
            "public_bucket": "public",
        },
    )
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "target-deployment-key")

    values, unreadable = service._decrypt_database_values_lenient("object_storage", stored)

    assert values["endpoint"] == "https://oss-cn-hangzhou.aliyuncs.com"
    assert values["secret_key"] == ""
    assert unreadable == ["secret_key"]
    with pytest.raises(service.InfrastructureSecretDecryptionError, match="重新填写密钥"):
        service._decrypt_database_values("object_storage", stored)


async def test_get_config_keeps_all_database_sources_when_one_secret_cannot_decrypt(monkeypatch):
    class FakeRow:
        def __init__(self, row_id, name, provider, values, *, active=True):
            self.id = row_id
            self.config_name = name
            self.provider = provider
            self.config_json = values
            self.is_active = active
            self.created_at = None
            self.updated_at = None

    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "source-deployment-key")
    object_values = service._encrypt_database_values(
        "object_storage",
        {
            "provider": "aliyun_oss",
            "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
            "access_key": "access",
            "secret_key": "source-secret",
            "region": "cn-hangzhou",
            "public_url": "",
            "secure": True,
            "documents_bucket": "documents",
            "public_bucket": "public",
            "console_url": "",
        },
    )
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "target-deployment-key")
    rows = {
        "object_storage": [FakeRow(1, "线上 OSS", "aliyun_oss", object_values)],
        "vector_database": [
            FakeRow(
                2,
                "本机 Milvus",
                "milvus",
                {
                    "provider": "milvus",
                    "uri": "http://milvus:19530",
                    "token": "",
                    "name": "openzetc",
                    "console_url": "",
                },
            )
        ],
        "graph_database": [
            FakeRow(
                3,
                "本机 Neo4j",
                "neo4j",
                {
                    "provider": "neo4j",
                    "uri": "bolt://graph:7687",
                    "username": "neo4j",
                    "password": "plain-test-password",
                    "name": "neo4j",
                    "console_url": "",
                },
            )
        ],
    }

    class FakeRepository:
        def __init__(self, _session):
            pass

        async def list(self, section):
            return rows[section]

    @asynccontextmanager
    async def fake_session_context():
        yield object()

    monkeypatch.setattr(service, "InfrastructureConfigRepository", FakeRepository)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", fake_session_context)
    monkeypatch.setattr(service.runtime_cache, "save_runtime_config", lambda _config: None)

    result = await service.get_infrastructure_config()

    assert [source["config_name"] for source in result["_sources"]["object_storage"]] == ["线上 OSS"]
    assert result["_sources"]["object_storage"][0]["requires_secret_reentry"] is True
    assert result["_sources"]["object_storage"][0]["values"]["secret_key"] == ""
    assert result["_sources"]["vector_database"][0]["config_name"] == "本机 Milvus"
    assert result["_sources"]["graph_database"][0]["config_name"] == "本机 Neo4j"
    assert result["_warnings"][0]["code"] == "secret_decryption_failed"


async def test_save_source_requires_and_reencrypts_migrated_secret(monkeypatch):
    class FakeRow:
        id = 7
        config_name = "生产 OSS"
        provider = "aliyun_oss"
        is_active = False
        created_at = None
        updated_at = None

    row = FakeRow()
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "source-deployment-key")
    row.config_json = service._encrypt_database_values(
        "object_storage",
        {
            "provider": "aliyun_oss",
            "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
            "access_key": "access",
            "secret_key": "source-secret",
            "region": "cn-hangzhou",
            "public_url": "",
            "secure": True,
            "documents_bucket": "documents",
            "public_bucket": "public",
            "console_url": "",
        },
    )
    monkeypatch.setenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "target-deployment-key")

    class FakeRepository:
        def __init__(self, _session):
            pass

        async def get(self, _section, _source_id):
            return row

        async def get_by_name(self, _section, _name):
            return row

        async def update(self, target, **changes):
            for key, value in changes.items():
                setattr(target, key, value)

    @asynccontextmanager
    async def fake_session_context():
        yield object()

    monkeypatch.setattr(service, "InfrastructureConfigRepository", FakeRepository)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", fake_session_context)

    common_values = {
        "provider": "aliyun_oss",
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "access_key": "access",
        "region": "cn-hangzhou",
        "public_url": "",
        "secure": True,
        "documents_bucket": "documents",
        "public_bucket": "public",
        "console_url": "",
    }
    with pytest.raises(service.InfrastructureSecretDecryptionError, match="重新填写密钥"):
        await service.save_infrastructure_source(
            "object_storage",
            "生产 OSS",
            {**common_values, "secret_key": "********"},
            source_id=row.id,
        )

    saved = await service.save_infrastructure_source(
        "object_storage",
        "生产 OSS",
        {**common_values, "secret_key": "target-secret"},
        source_id=row.id,
    )

    assert saved["requires_secret_reentry"] is False
    assert saved["values"]["secret_key"] == "********"
    assert service._decrypt_database_values("object_storage", row.config_json)["secret_key"] == ("target-secret")


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
