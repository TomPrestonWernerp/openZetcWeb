from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.routers.system_router import system
from server.utils.auth_middleware import get_superadmin_user

pytestmark = pytest.mark.unit


def test_discovery_endpoint_is_public(monkeypatch):
    monkeypatch.setattr("server.routers.system_router.get_version", lambda: "0.7.1.dev0")

    app = FastAPI()
    app.include_router(system, prefix="/api")
    response = TestClient(app).get("/api/system/discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Yuxi"
    assert payload["version"] == "0.7.1.dev0"
    assert payload["api_prefix"] == "/api"
    assert payload["capabilities"]["cli"]["browser_login"] is True
    assert payload["capabilities"]["cli"]["api_key_auth"] is True
    assert payload["capabilities"]["cli"]["kb_upload"] is True
    assert payload["endpoints"]["cli_auth_sessions"] == "/api/auth/cli/sessions"


def test_desktop_release_uses_latest_update_manifests(httpx_mock):
    httpx_mock.add_response(
        url="https://github.com/TomPrestonWernerp/openZetcX/releases/latest/download/latest.yml",
        text="""version: 0.6.0
files:
  - url: openZetcX-0.6.0-Windows-x64.exe
""",
    )
    httpx_mock.add_response(
        url="https://github.com/TomPrestonWernerp/openZetcX/releases/latest/download/latest-mac.yml",
        text="""version: 0.6.0
files:
  - url: openZetcX-0.6.0-macOS-arm64.zip
  - url: openZetcX-0.6.0-macOS-arm64.dmg
  - url: openZetcX-0.6.0-macOS-x64.zip
  - url: openZetcX-0.6.0-macOS-x64.dmg
""",
    )

    app = FastAPI()
    app.include_router(system, prefix="/api")
    response = TestClient(app).get("/api/system/desktop-release")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["tag_name"] == "v0.6.0"
    assert [asset["name"] for asset in payload["assets"]] == [
        "openZetcX-0.6.0-Windows-x64.exe",
        "openZetcX-0.6.0-macOS-arm64.dmg",
        "openZetcX-0.6.0-macOS-x64.dmg",
    ]
    assert all("/releases/latest/download/" in asset["browser_download_url"] for asset in payload["assets"])


def test_infrastructure_config_endpoint_uses_superadmin_service(monkeypatch):
    expected = {
        "object_storage": {"provider": "minio", "secret_key": "********"},
        "vector_database": {"provider": "milvus", "token": ""},
        "graph_database": {"provider": "neo4j", "password": "********"},
    }
    async def get_expected_config():
        return expected

    monkeypatch.setattr(
        "yuxi.services.infrastructure_config_service.get_infrastructure_config",
        get_expected_config,
    )

    app = FastAPI()
    app.include_router(system, prefix="/api")
    app.dependency_overrides[get_superadmin_user] = lambda: object()
    response = TestClient(app).get("/api/system/infrastructure-config")

    assert response.status_code == 200
    assert response.json() == expected


def test_infrastructure_config_endpoint_rejects_non_superadmin():
    def reject_non_superadmin():
        raise HTTPException(status_code=403, detail="需要超级管理员权限")

    app = FastAPI()
    app.include_router(system, prefix="/api")
    app.dependency_overrides[get_superadmin_user] = reject_non_superadmin
    response = TestClient(app).get("/api/system/infrastructure-config")

    assert response.status_code == 403


def test_infrastructure_source_save_activate_and_delete_endpoints(monkeypatch):
    calls = []

    async def save_source(section, config_name, values, *, source_id=None, updated_by_uid=None):
        calls.append(("save", section, config_name, source_id, updated_by_uid, values["provider"]))
        return {"id": 12, "config_name": config_name, "is_active": False}

    async def activate_source(section, source_id):
        calls.append(("activate", section, source_id))
        return {"section": section, "active_id": source_id}

    async def delete_source(section, source_id):
        calls.append(("delete", section, source_id))
        return {"section": section, "deleted_id": source_id}

    monkeypatch.setattr(
        "yuxi.services.infrastructure_config_service.save_infrastructure_source",
        save_source,
    )
    monkeypatch.setattr(
        "yuxi.services.infrastructure_config_service.activate_infrastructure_source",
        activate_source,
    )
    monkeypatch.setattr(
        "yuxi.services.infrastructure_config_service.delete_infrastructure_source",
        delete_source,
    )

    app = FastAPI()
    app.include_router(system, prefix="/api")
    app.dependency_overrides[get_superadmin_user] = lambda: SimpleNamespace(uid="superadmin-1")
    client = TestClient(app)

    save_response = client.post(
        "/api/system/infrastructure-config/sources",
        json={
            "section": "object_storage",
            "config_name": "生产 OSS",
            "source_id": None,
            "values": {"provider": "aliyun_oss"},
        },
    )
    activate_response = client.post(
        "/api/system/infrastructure-config/activate",
        json={"section": "object_storage", "source_id": 12},
    )
    delete_response = client.post(
        "/api/system/infrastructure-config/delete",
        json={"section": "object_storage", "source_id": 12},
    )

    assert save_response.status_code == 200
    assert activate_response.status_code == 200
    assert delete_response.status_code == 200
    assert calls == [
        ("save", "object_storage", "生产 OSS", None, "superadmin-1", "aliyun_oss"),
        ("activate", "object_storage", 12),
        ("delete", "object_storage", 12),
    ]
