from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from pymilvus import connections, db
from sqlalchemy import text

from yuxi.config import cache as runtime_cache
from yuxi.config import config
from yuxi.config.app import INFRASTRUCTURE_CONFIG_FIELDS, INFRASTRUCTURE_PROVIDERS
from yuxi.repositories.infrastructure_config_repository import InfrastructureConfigRepository
from yuxi.storage.minio.client import MinIOClient
from yuxi.storage.neo4j.manager import Neo4jConnectionManager
from yuxi.storage.postgres.manager import pg_manager

REVEALABLE_SECRET_FIELDS = {
    "object_storage": {"secret_key": "object_storage_secret_key"},
    "vector_database": {"token": "vector_database_token"},
    "graph_database": {"password": "graph_database_password"},
}
ENCRYPTED_VALUE_PREFIX = "enc:v1:"
SYSTEM_DEFAULT_SECRET = "__OPENZETC_SYSTEM_DEFAULT_SECRET__"


def _local_minio_defaults(*, masked: bool) -> dict:
    model_fields = type(config).model_fields
    secret_key = os.getenv("MINIO_SECRET_KEY") or model_fields["object_storage_secret_key"].default
    return {
        "provider": "minio",
        "endpoint": os.getenv("MINIO_URI") or model_fields["object_storage_endpoint"].default,
        "access_key": os.getenv("MINIO_ACCESS_KEY") or model_fields["object_storage_access_key"].default,
        "secret_key": "********" if masked else secret_key,
        "region": "",
        "public_url": os.getenv("MINIO_PUBLIC_URL") or model_fields["object_storage_public_url"].default,
        "secure": False,
        "documents_bucket": model_fields["object_storage_documents_bucket"].default,
        "public_bucket": model_fields["object_storage_public_bucket"].default,
        "console_url": model_fields["object_storage_console_url"].default,
    }


def _resolve_infrastructure_values(
    section: str,
    values: dict | None = None,
    *,
    base_values: dict | None = None,
) -> dict:
    """合并来源草稿；掩码保留原密钥，本机服务可回退到部署环境默认值。"""
    resolved = dict(base_values or config.resolve_infrastructure_config(section))
    allowed_keys = {
        field.removeprefix(f"{section}_") for field in INFRASTRUCTURE_CONFIG_FIELDS.get(section, ())
    }
    for key, value in dict(values or {}).items():
        if key not in allowed_keys:
            raise ValueError(f"未知配置项: {key}")
        if key in REVEALABLE_SECRET_FIELDS.get(section, {}) and value == "********":
            continue
        resolved[key] = value

    provider = resolved.get("provider")
    if section == "object_storage" and provider == "minio":
        local_defaults = _local_minio_defaults(masked=False)
        for field in ("access_key", "secret_key"):
            if not str(resolved.get(field) or "").strip() or resolved.get(field) == SYSTEM_DEFAULT_SECRET:
                resolved[field] = local_defaults[field]
    return config.resolve_infrastructure_config(section, resolved)


def _get_cipher() -> Fernet:
    """使用部署级稳定密钥派生数据库配置加密密钥。"""
    key_material = (
        os.getenv("INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY", "").strip()
        or os.getenv("JWT_SECRET_KEY", "").strip()
    )
    if not key_material:
        raise RuntimeError(
            "未配置 INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY 或 JWT_SECRET_KEY，无法安全保存基础设施密钥"
        )
    derived = hashlib.sha256(f"openzetc:infrastructure:{key_material}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _encrypt_database_values(section: str, values: dict) -> dict:
    encrypted = dict(values)
    cipher = _get_cipher()
    for field in REVEALABLE_SECRET_FIELDS.get(section, {}):
        value = encrypted.get(field)
        if value:
            encrypted[field] = ENCRYPTED_VALUE_PREFIX + cipher.encrypt(str(value).encode()).decode()
    return encrypted


def _decrypt_database_values(section: str, values: dict) -> dict:
    decrypted = dict(values or {})
    cipher = None
    for field in REVEALABLE_SECRET_FIELDS.get(section, {}):
        value = decrypted.get(field)
        if not isinstance(value, str) or not value.startswith(ENCRYPTED_VALUE_PREFIX):
            continue
        try:
            cipher = cipher or _get_cipher()
            decrypted[field] = cipher.decrypt(value.removeprefix(ENCRYPTED_VALUE_PREFIX).encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError(f"基础设施配置密钥无法解密: {section}.{field}") from exc
    return decrypted


DEFAULT_SOURCE_NAMES = {
    "object_storage": "默认对象存储",
    "vector_database": "默认向量数据库",
    "graph_database": "默认图数据库",
}


def _mask_secret_values(section: str, values: dict) -> dict:
    masked = dict(values or {})
    for field in REVEALABLE_SECRET_FIELDS.get(section, {}):
        if masked.get(field):
            masked[field] = "********"
    return masked


def _serialize_source(section: str, row) -> dict:
    values = _decrypt_database_values(section, row.config_json)
    return {
        "id": row.id,
        "config_name": row.config_name,
        "provider": row.provider,
        "is_active": bool(row.is_active),
        "values": _mask_secret_values(section, values),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _read_legacy_configs(session) -> dict[str, dict]:
    """读取旧 infrastructure_configs 表；表不存在时返回空字典。"""
    exists = await session.execute(text("SELECT to_regclass('public.infrastructure_configs')"))
    if exists.scalar() is None:
        return {}
    result = await session.execute(text("SELECT section, config_json FROM infrastructure_configs"))
    return {str(row.section): dict(row.config_json or {}) for row in result}


async def initialize_infrastructure_config() -> dict:
    """创建三类默认来源、迁移旧单表，并加载每类激活来源。"""
    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        legacy_configs = await _read_legacy_configs(session)
        for section in INFRASTRUCTURE_CONFIG_FIELDS:
            if await repository.count(section) == 0:
                stored_values = legacy_configs.get(section)
                values = (
                    _decrypt_database_values(section, stored_values)
                    if stored_values
                    else config.resolve_infrastructure_config(section)
                )
                await repository.create(
                    section,
                    config_name=DEFAULT_SOURCE_NAMES[section],
                    provider=str(values.get("provider") or ""),
                    config_json=_encrypt_database_values(section, values),
                    is_active=True,
                )

            active = await repository.get_active(section)
            if active is None:
                rows = await repository.list(section)
                active = await repository.activate(section, rows[0].id)
            config.update_infrastructure_config(
                section,
                _decrypt_database_values(section, active.config_json),
            )

        # 新表均已存在且至少有一个激活来源后，旧单表不再保留。
        await session.execute(text("DROP TABLE IF EXISTS infrastructure_configs"))

    # 清理旧 TOML 中可能存在的基础设施字段，同时发布当前激活配置快照。
    config.save()
    runtime_cache.save_runtime_config(config)
    return await get_infrastructure_config()


async def get_infrastructure_config() -> dict:
    """返回三类激活配置以及每类全部已保存来源，敏感字段统一脱敏。"""
    result: dict = {"_sources": {}, "_local_defaults": {"object_storage": _local_minio_defaults(masked=True)}}
    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        for section in INFRASTRUCTURE_CONFIG_FIELDS:
            rows = await repository.list(section)
            active = next((row for row in rows if row.is_active), None)
            if active is not None:
                active_values = _decrypt_database_values(section, active.config_json)
                config.update_infrastructure_config(section, active_values)
                result[section] = _mask_secret_values(section, active_values)
            else:
                result[section] = config.dump_infrastructure_config()[section]
            result["_sources"][section] = [_serialize_source(section, row) for row in rows]
    runtime_cache.save_runtime_config(config)
    return result


async def save_infrastructure_source(
    section: str,
    config_name: str,
    values: dict,
    *,
    source_id: int | None = None,
    updated_by_uid: str | None = None,
) -> dict:
    """新增或修改一条命名来源；修改激活来源时同步运行时连接。"""
    clean_name = str(config_name or "").strip()
    if not clean_name:
        raise ValueError("配置名称不能为空")
    if len(clean_name) > 100:
        raise ValueError("配置名称不能超过 100 个字符")

    should_sync_runtime = False
    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        row = await repository.get(section, source_id) if source_id is not None else None
        if source_id is not None and row is None:
            raise ValueError("配置来源不存在")
        duplicate = await repository.get_by_name(section, clean_name)
        if duplicate is not None and (row is None or duplicate.id != row.id):
            raise ValueError("同一类型下配置名称不能重复")

        base_values = _decrypt_database_values(section, row.config_json) if row is not None else None
        resolved = _resolve_infrastructure_values(section, values, base_values=base_values)
        _validate(section, resolved)
        encrypted = _encrypt_database_values(section, resolved)
        if row is None:
            row = await repository.create(
                section,
                config_name=clean_name,
                provider=resolved["provider"],
                config_json=encrypted,
                is_active=(await repository.count(section) == 0),
                updated_by_uid=updated_by_uid,
            )
        else:
            await repository.update(
                row,
                config_name=clean_name,
                provider=resolved["provider"],
                config_json=encrypted,
                updated_by_uid=updated_by_uid,
            )
        should_sync_runtime = bool(row.is_active)
        response = _serialize_source(section, row)

    if should_sync_runtime:
        config.update_infrastructure_config(section, resolved)
        runtime_cache.save_runtime_config(config)
    return response


async def save_infrastructure_config(section: str, values: dict, *, updated_by_uid: str | None = None) -> dict:
    """兼容旧客户端：更新当前激活来源，并返回旧格式的激活配置快照。"""
    async with pg_manager.get_async_session_context() as session:
        active = await InfrastructureConfigRepository(session).get_active(section)
    await save_infrastructure_source(
        section,
        active.config_name if active else DEFAULT_SOURCE_NAMES[section],
        values,
        source_id=active.id if active else None,
        updated_by_uid=updated_by_uid,
    )
    return await get_infrastructure_config()


async def activate_infrastructure_source(section: str, source_id: int) -> dict:
    """激活已保存来源。激活仅切换连接，不自动迁移已有数据。"""
    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        row = await repository.get(section, source_id)
        if row is None:
            raise ValueError("配置来源不存在")
        values = _decrypt_database_values(section, row.config_json)
        await repository.activate(section, source_id)

    config.update_infrastructure_config(section, values)
    runtime_cache.save_runtime_config(config)
    return {"section": section, "active_id": source_id, "message": "已激活"}


async def delete_infrastructure_source(section: str, source_id: int) -> dict:
    """删除未激活来源；激活来源必须先切换后才能删除。"""
    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        row = await repository.get(section, source_id)
        if row is None:
            raise ValueError("配置来源不存在")
        if row.is_active:
            raise ValueError("当前激活配置不能删除，请先激活其他来源")
        await repository.delete(section, source_id)
    return {"section": section, "deleted_id": source_id, "message": "已删除"}


async def reveal_infrastructure_secret(
    section: str,
    field: str,
    *,
    source: str | None = None,
    source_id: int | None = None,
) -> dict[str, str]:
    """按来源从数据库读取并解密一个允许查看的敏感字段。"""
    if field not in REVEALABLE_SECRET_FIELDS.get(section, {}):
        raise ValueError("不支持查看该配置项")

    if source == "local_default":
        if section != "object_storage" or field != "secret_key":
            raise ValueError("该配置项没有本机默认密钥")
        value = _local_minio_defaults(masked=False)["secret_key"]
        return {"section": section, "field": field, "value": str(value or "")}

    async with pg_manager.get_async_session_context() as session:
        repository = InfrastructureConfigRepository(session)
        row = (
            await repository.get(section, source_id)
            if source_id is not None
            else await repository.get_active(section)
        )
        if row is None:
            raise ValueError("配置尚未保存")
        values = _decrypt_database_values(section, row.config_json)
    return {"section": section, "field": field, "value": str(values.get(field) or "")}


async def test_infrastructure_connection(section: str, values: dict) -> dict[str, str]:
    resolved = _resolve_infrastructure_values(section, values)
    _validate(section, resolved)

    if section == "object_storage":
        client = MinIOClient(resolved)
        bucket_names = {resolved["documents_bucket"], resolved["public_bucket"]}
        missing_buckets = []
        for bucket_name in bucket_names:
            exists = await asyncio.to_thread(client.client.bucket_exists, bucket_name)
            if not exists:
                missing_buckets.append(bucket_name)
        if missing_buckets:
            raise ValueError(f"连接成功，但 Bucket 不存在: {', '.join(sorted(missing_buckets))}")
    elif section == "vector_database":
        await asyncio.to_thread(_test_milvus, resolved)
    elif section == "graph_database":
        await asyncio.to_thread(_test_neo4j, resolved)
    else:
        raise ValueError(f"不支持的基础设施配置类型: {section}")

    return {"section": section, "status": "ok", "message": "连接成功"}


def _validate(section: str, values: dict) -> None:
    providers = INFRASTRUCTURE_PROVIDERS.get(section)
    if providers is None:
        raise ValueError(f"不支持的基础设施配置类型: {section}")
    if values.get("provider") not in providers:
        raise ValueError(f"不支持的供应商: {values.get('provider')}")

    required = {
        "object_storage": ("endpoint", "access_key", "secret_key", "documents_bucket", "public_bucket"),
        "vector_database": ("uri", "name"),
        "graph_database": ("uri", "username", "password", "name"),
    }[section]
    if section == "vector_database" and values.get("provider") in {"zilliz", "aliyun_milvus"}:
        required = (*required, "token")
    missing = [key for key in required if not str(values.get(key) or "").strip()]
    if missing:
        raise ValueError(f"缺少必填配置: {', '.join(missing)}")


def _test_milvus(settings: dict) -> None:
    alias = f"infrastructure_test_{uuid4().hex}"
    try:
        connections.connect(alias=alias, uri=settings["uri"], token=settings.get("token") or "")
        databases = db.list_database(using=alias)
        if settings["name"] not in databases:
            raise ValueError(f"连接成功，但向量数据库不存在: {settings['name']}")
    finally:
        if connections.has_connection(alias):
            connections.disconnect(alias)


def _test_neo4j(settings: dict) -> None:
    connection = Neo4jConnectionManager(settings)
    connection.close()
