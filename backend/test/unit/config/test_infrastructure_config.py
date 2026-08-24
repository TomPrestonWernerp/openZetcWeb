from __future__ import annotations

import importlib

import pytest
import tomli

from openzetc.config.app import MASKED_SECRET, Config
from openzetc.storage.postgres.models_business import (
    GraphDatabaseConfig,
    ObjectStorageConfig,
    VectorDatabaseConfig,
)

pytestmark = pytest.mark.unit


def test_infrastructure_config_is_separate_and_secrets_are_masked(tmp_path):
    cfg = Config(save_dir=str(tmp_path))

    assert "object_storage_provider" not in cfg.dump_config()
    infrastructure = cfg.dump_infrastructure_config()
    assert infrastructure["object_storage"]["provider"] == "minio"
    assert infrastructure["object_storage"]["access_key"] == cfg.object_storage_access_key
    assert infrastructure["object_storage"]["secret_key"] == MASKED_SECRET
    assert infrastructure["vector_database"]["token"] in {"", MASKED_SECRET}
    assert infrastructure["graph_database"]["password"] == MASKED_SECRET


def test_masked_secret_keeps_existing_value_when_updating(tmp_path):
    cfg = Config(save_dir=str(tmp_path))
    old_secret = cfg.object_storage_secret_key

    cfg.update_infrastructure_config(
        "object_storage",
        {
            "provider": "aws_s3",
            "endpoint": "https://s3.example.com",
            "secret_key": MASKED_SECRET,
            "secure": True,
        },
    )

    assert cfg.object_storage_provider == "aws_s3"
    assert cfg.object_storage_endpoint == "https://s3.example.com"
    assert cfg.object_storage_secret_key == old_secret
    assert cfg.object_storage_secure is True


def test_generic_config_update_cannot_change_infrastructure(tmp_path):
    cfg = Config(save_dir=str(tmp_path))

    cfg.update({"object_storage_endpoint": "https://untrusted.example.com"})

    assert cfg.object_storage_endpoint != "https://untrusted.example.com"


def test_infrastructure_config_rejects_unknown_provider(tmp_path):
    cfg = Config(save_dir=str(tmp_path))

    with pytest.raises(ValueError, match="不支持的供应商"):
        cfg.update_infrastructure_config("vector_database", {"provider": "unknown"})


def test_infrastructure_config_is_not_written_to_toml(tmp_path, monkeypatch):
    config_module = importlib.import_module("openzetc.config.app")
    monkeypatch.setattr(config_module.runtime_cache, "save_runtime_config", lambda _config: None)
    cfg = Config(save_dir=str(tmp_path))
    cfg.update_infrastructure_config(
        "object_storage",
        {"endpoint": "https://storage.example.com", "secret_key": "database-only-secret"},
    )

    cfg.save()

    with open(tmp_path / "config" / "base.toml", "rb") as config_file:
        persisted = tomli.load(config_file)
    assert not any(key.startswith("object_storage_") for key in persisted)
    assert "database-only-secret" not in (tmp_path / "config" / "base.toml").read_text(encoding="utf-8")


def test_infrastructure_sources_use_three_distinct_tables_with_single_active_indexes():
    models = (ObjectStorageConfig, VectorDatabaseConfig, GraphDatabaseConfig)

    assert [model.__tablename__ for model in models] == [
        "object_storage_configs",
        "vector_database_configs",
        "graph_database_configs",
    ]
    for model in models:
        assert {"config_name", "provider", "config_json", "is_active"}.issubset(model.__table__.columns.keys())
        active_indexes = [index for index in model.__table__.indexes if index.name.endswith("_one_active")]
        assert len(active_indexes) == 1
        assert active_indexes[0].unique is True
