from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routers.system_router import system

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
