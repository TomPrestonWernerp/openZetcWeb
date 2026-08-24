"""应用配置模块。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomli
import tomli_w
from pydantic import BaseModel, Field, PrivateAttr

from yuxi.config import cache as runtime_cache
from yuxi.knowledge.parser.registry import PROCESSOR_TYPES
from yuxi.utils.logging_config import logger

READONLY_CONFIG_FIELDS = frozenset({"save_dir"})
DEFAULT_OCR_ENGINE = "rapid_ocr"
MASKED_SECRET = "********"
INFRASTRUCTURE_CONFIG_FIELDS = {
    "object_storage": (
        "object_storage_provider",
        "object_storage_endpoint",
        "object_storage_access_key",
        "object_storage_secret_key",
        "object_storage_region",
        "object_storage_public_url",
        "object_storage_secure",
        "object_storage_documents_bucket",
        "object_storage_public_bucket",
        "object_storage_console_url",
    ),
    "vector_database": (
        "vector_database_provider",
        "vector_database_uri",
        "vector_database_token",
        "vector_database_name",
        "vector_database_console_url",
    ),
    "graph_database": (
        "graph_database_provider",
        "graph_database_uri",
        "graph_database_username",
        "graph_database_password",
        "graph_database_name",
        "graph_database_console_url",
    ),
}
SENSITIVE_INFRASTRUCTURE_FIELDS = frozenset(
    {
        "object_storage_secret_key",
        "vector_database_token",
        "graph_database_password",
    }
)
INFRASTRUCTURE_PROVIDERS = {
    "object_storage": {"minio", "aws_s3", "aliyun_oss", "tencent_cos", "qiniu_kodo", "s3_compatible"},
    "vector_database": {"milvus", "zilliz", "aliyun_milvus", "milvus_compatible"},
    "graph_database": {"neo4j", "neo4j_aura", "neo4j_compatible"},
}


def _get_available_ocr_engines() -> set[str]:
    return {"disable", *PROCESSOR_TYPES}


def _normalize_default_ocr_engine(value: Any) -> str:
    engine = str(value or "").strip() or DEFAULT_OCR_ENGINE
    if engine not in _get_available_ocr_engines():
        raise ValueError(f"不支持的默认 OCR 引擎: {engine}")
    return engine


class Config(BaseModel):
    """应用配置类。

    `save_dir` 只在启动时决定配置文件位置，运行时不可修改。通用配置写入
    `base.toml`；基础设施配置以 PostgreSQL 为权威存储。两类配置都会同步到 Redis
    快照（`yuxi:runtime_config`），其他进程通过后台线程刷新内存值。
    """

    save_dir: str = Field(default="saves", description="保存目录", exclude=True)
    enable_content_guard: bool = Field(default=False, description="是否启用内容审查")
    enable_content_guard_llm: bool = Field(default=False, description="是否启用LLM内容审查")
    default_model: str = Field(
        default="siliconflow-cn:Pro/MiniMaxAI/MiniMax-M2.5",
        description="默认对话模型",
    )
    fast_model: str = Field(
        default="siliconflow-cn:Pro/MiniMaxAI/MiniMax-M2.5",
        description="快速响应模型",
    )
    embed_model: str = Field(
        default="siliconflow-cn:Pro/BAAI/bge-m3",
        description="默认 Embedding 模型",
    )
    reranker: str = Field(
        default="siliconflow-cn:Pro/BAAI/bge-reranker-v2-m3",
        description="默认 Re-Ranker 模型",
    )
    content_guard_llm_model: str = Field(
        default="siliconflow-cn:Pro/MiniMaxAI/MiniMax-M2.5",
        description="内容审查LLM模型",
    )
    default_ocr_engine: str = Field(default=DEFAULT_OCR_ENGINE, description="默认 OCR 解析引擎")

    # 基础设施配置仅通过超级管理员专用接口读取和修改，不包含在通用配置响应中。
    object_storage_provider: str = Field(default="minio", description="对象存储供应商")
    object_storage_endpoint: str = Field(default="http://minio:9000", description="对象存储服务地址")
    object_storage_access_key: str = Field(default="minioadmin", description="对象存储 Access Key")
    object_storage_secret_key: str = Field(default="minioadmin", description="对象存储 Secret Key")
    object_storage_region: str = Field(default="", description="对象存储区域")
    object_storage_public_url: str = Field(default="/minio", description="对象存储公开访问地址")
    object_storage_secure: bool = Field(default=False, description="对象存储是否使用 HTTPS")
    object_storage_documents_bucket: str = Field(default="knowledgebases", description="知识文件存储桶")
    object_storage_public_bucket: str = Field(default="public", description="公开图片存储桶")
    object_storage_console_url: str = Field(default="http://localhost:9001", description="对象存储控制台地址")

    vector_database_provider: str = Field(default="milvus", description="向量数据库供应商")
    vector_database_uri: str = Field(default="http://milvus:19530", description="向量数据库连接地址")
    vector_database_token: str = Field(default="", description="向量数据库 Token")
    vector_database_name: str = Field(default="yuxi", description="向量数据库名称")
    vector_database_console_url: str = Field(default="http://localhost:9091/webui/", description="向量数据库控制台地址")

    graph_database_provider: str = Field(default="neo4j", description="图数据库供应商")
    graph_database_uri: str = Field(default="bolt://graph:7687", description="图数据库连接地址")
    graph_database_username: str = Field(default="neo4j", description="图数据库用户名")
    graph_database_password: str = Field(default="0123456789", description="图数据库密码")
    graph_database_name: str = Field(default="neo4j", description="图数据库名称")
    graph_database_console_url: str = Field(default="http://localhost:7474/", description="图数据库控制台地址")

    _config_file: Path | None = PrivateAttr(default=None)
    _runtime_sync_thread: Any = PrivateAttr(default=None)
    _infrastructure_environment_defaults: dict[str, Any] = PrivateAttr(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    def __init__(self, **data):
        super().__init__(**data)
        self._setup_paths()
        self._load_infrastructure_environment_defaults()
        self._load_user_config()

    def _load_infrastructure_environment_defaults(self) -> None:
        env_values = {
            "object_storage_endpoint": os.getenv("MINIO_URI"),
            "object_storage_access_key": os.getenv("MINIO_ACCESS_KEY"),
            "object_storage_secret_key": os.getenv("MINIO_SECRET_KEY"),
            "object_storage_public_url": os.getenv("MINIO_PUBLIC_URL"),
            "vector_database_uri": os.getenv("MILVUS_URI"),
            "vector_database_token": os.getenv("MILVUS_TOKEN"),
            "vector_database_name": os.getenv("MILVUS_DB") or os.getenv("MILVUS_DB_NAME"),
            "graph_database_uri": os.getenv("NEO4J_URI"),
            "graph_database_username": os.getenv("NEO4J_USERNAME"),
            "graph_database_password": os.getenv("NEO4J_PASSWORD"),
            "graph_database_name": os.getenv("NEO4J_DATABASE"),
        }
        for key, value in env_values.items():
            if value is not None:
                setattr(self, key, value)
                self._infrastructure_environment_defaults[key] = value

    def _setup_paths(self) -> None:
        self._config_file = Path(self.save_dir) / "config" / "base.toml"
        self._config_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_user_config(self) -> None:
        if not self._config_file or not self._config_file.exists():
            logger.info(f"Config file not found, using defaults: {self._config_file}")
            return

        logger.info(f"Loading config from {self._config_file}")
        try:
            with open(self._config_file, "rb") as f:
                user_config = tomli.load(f)

            for key, value in user_config.items():
                if key in READONLY_CONFIG_FIELDS:
                    logger.warning(f"Readonly config key ignored: {key}")
                elif key in type(self).model_fields:
                    try:
                        setattr(self, key, self._normalize_config_value(key, value))
                    except ValueError as exc:
                        logger.warning(f"Invalid config key ignored: {key} ({exc})")
                else:
                    logger.warning(f"Unknown config key: {key}")

        except Exception as e:
            logger.error(f"Failed to load config from {self._config_file}: {e}")

    def start_runtime_sync(self, interval: float = runtime_cache.RUNTIME_CONFIG_SYNC_INTERVAL_SECONDS) -> None:
        """启动后台线程周期性从 Redis 同步运行时配置。多次调用仅启动一次。"""
        self._runtime_sync_thread = runtime_cache.start_runtime_sync(
            self,
            self._runtime_sync_thread,
            interval=interval,
        )

    def refresh(self) -> None:
        """从 Redis 快照刷新公开配置字段到内存；Redis 不可用或无快照时保持当前值。"""
        runtime_cache.refresh_runtime_config(self)

    def save(self) -> None:
        if not self._config_file:
            logger.warning("Config file path not set")
            return

        logger.info(f"Saving config to {self._config_file}")
        infrastructure_fields = {field for fields in INFRASTRUCTURE_CONFIG_FIELDS.values() for field in fields}
        user_modified = {}
        for field_name, field_info in type(self).model_fields.items():
            if field_info.exclude or field_name in infrastructure_fields:
                continue
            current_value = getattr(self, field_name)
            effective_default = self._infrastructure_environment_defaults.get(field_name, field_info.default)
            if current_value != effective_default:
                user_modified[field_name] = current_value

        try:
            with open(self._config_file, "wb") as f:
                tomli_w.dump(user_modified, f)
            logger.info(f"Config saved to {self._config_file}")
            runtime_cache.save_runtime_config(self)
        except Exception as e:
            logger.error(f"Failed to save config to {self._config_file}: {e}")

    def dump_config(self) -> dict[str, Any]:
        config_dict = self.model_dump()
        infrastructure_fields = {field for fields in INFRASTRUCTURE_CONFIG_FIELDS.values() for field in fields}
        for field_name in infrastructure_fields:
            config_dict.pop(field_name, None)
        fields_info = {}
        for field_name, field_info in Config.model_fields.items():
            if field_info.exclude or field_name in infrastructure_fields:
                continue
            fields_info[field_name] = {
                "des": field_info.description,
                "default": field_info.default,
                "type": field_info.annotation.__name__
                if hasattr(field_info.annotation, "__name__")
                else str(field_info.annotation),
                "exclude": field_info.exclude if hasattr(field_info, "exclude") else False,
            }
        config_dict["_config_items"] = fields_info
        return config_dict

    def dump_infrastructure_config(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for section, field_names in INFRASTRUCTURE_CONFIG_FIELDS.items():
            values = {}
            for field_name in field_names:
                key = field_name.removeprefix(f"{section}_")
                value = getattr(self, field_name)
                values[key] = MASKED_SECRET if field_name in SENSITIVE_INFRASTRUCTURE_FIELDS and value else value
            result[section] = values
        return result

    def resolve_infrastructure_config(self, section: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        if section not in INFRASTRUCTURE_CONFIG_FIELDS:
            raise ValueError(f"不支持的基础设施配置类型: {section}")

        resolved = {
            field_name.removeprefix(f"{section}_"): getattr(self, field_name)
            for field_name in INFRASTRUCTURE_CONFIG_FIELDS[section]
        }
        for key, value in (values or {}).items():
            field_name = f"{section}_{key}"
            if field_name not in INFRASTRUCTURE_CONFIG_FIELDS[section]:
                raise ValueError(f"未知配置项: {key}")
            if field_name in SENSITIVE_INFRASTRUCTURE_FIELDS and value == MASKED_SECRET:
                continue
            resolved[key] = value
        return resolved

    def update_infrastructure_config(self, section: str, values: dict[str, Any]) -> None:
        resolved = self.resolve_infrastructure_config(section, values)
        provider = str(resolved.get("provider") or "").strip()
        if provider not in INFRASTRUCTURE_PROVIDERS[section]:
            raise ValueError(f"不支持的供应商: {provider}")

        for field_name in INFRASTRUCTURE_CONFIG_FIELDS[section]:
            key = field_name.removeprefix(f"{section}_")
            value = resolved[key]
            if isinstance(value, str):
                value = value.strip()
            setattr(self, field_name, value)

    def infrastructure_signature(self, section: str) -> tuple[Any, ...]:
        return tuple(self.resolve_infrastructure_config(section).values())

    def update(self, other: dict[str, Any]) -> None:
        infrastructure_fields = {field for fields in INFRASTRUCTURE_CONFIG_FIELDS.values() for field in fields}
        for key, value in other.items():
            if key in infrastructure_fields:
                logger.warning(f"Infrastructure config key ignored by generic updater: {key}")
            elif self.can_update(key):
                self.set_value(key, value)
            elif key in READONLY_CONFIG_FIELDS:
                logger.warning(f"Readonly config key ignored: {key}")
            else:
                logger.warning(f"Unknown config key: {key}")

    def can_update(self, key: object) -> bool:
        infrastructure_fields = {field for fields in INFRASTRUCTURE_CONFIG_FIELDS.values() for field in fields}
        return (
            isinstance(key, str)
            and key in type(self).model_fields
            and key not in READONLY_CONFIG_FIELDS
            and key not in infrastructure_fields
        )

    def set_value(self, key: str, value: Any) -> None:
        if not self.can_update(key):
            raise ValueError(f"配置项不可修改: {key}")
        setattr(self, key, self._normalize_config_value(key, value))

    def _normalize_config_value(self, key: str, value: Any) -> Any:
        if key == "default_ocr_engine":
            return _normalize_default_ocr_engine(value)
        return value


config = Config()
