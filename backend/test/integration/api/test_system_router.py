"""
Integration tests for system router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_health_endpoint_is_public(test_client):
    response = await test_client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_info_endpoint_is_public(test_client):
    response = await test_client.get("/api/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "data" in payload


async def test_config_get_requires_login_and_update_requires_admin(test_client, standard_user):
    assert (await test_client.get("/api/system/config")).status_code == 401
    user_config_response = await test_client.get("/api/system/config", headers=standard_user["headers"])
    assert user_config_response.status_code == 200, user_config_response.text

    update_response = await test_client.post(
        "/api/system/config/update",
        json={"default_ocr_engine": "rapid_ocr"},
        headers=standard_user["headers"],
    )
    assert update_response.status_code == 403


async def test_admin_can_fetch_config_and_reload_info(test_client, admin_headers):
    config_response = await test_client.get("/api/system/config", headers=admin_headers)
    assert config_response.status_code == 200, config_response.text
    assert isinstance(config_response.json(), dict)

    reload_response = await test_client.post("/api/system/info/reload", headers=admin_headers)
    assert reload_response.status_code == 200, reload_response.text
    reload_payload = reload_response.json()
    assert reload_payload["success"] is True
    assert "data" in reload_payload


async def test_sandbox_config_is_environment_only(test_client, admin_headers):
    config_response = await test_client.get("/api/system/config", headers=admin_headers)
    assert config_response.status_code == 200, config_response.text
    sandbox_fields = {
        "sandbox_provider",
        "sandbox_provisioner_url",
        "sandbox_provisioner_token",
        "sandbox_virtual_path_prefix",
        "sandbox_exec_timeout_seconds",
        "sandbox_max_output_bytes",
        "sandbox_keepalive_interval_seconds",
    }
    assert sandbox_fields.isdisjoint(config_response.json())
    assert sandbox_fields.isdisjoint(config_response.json()["_config_items"])

    update_response = await test_client.post(
        "/api/system/config",
        json={"key": "sandbox_provisioner_url", "value": "http://other:8002"},
        headers=admin_headers,
    )
    assert update_response.status_code == 400
    assert update_response.json()["detail"] == "未知配置项: sandbox_provisioner_url"


async def test_infrastructure_config_requires_superadmin_and_tests_local_services(
    test_client, admin_headers, standard_user
):
    denied_response = await test_client.get(
        "/api/system/infrastructure-config",
        headers=standard_user["headers"],
    )
    assert denied_response.status_code == 403

    config_response = await test_client.get("/api/system/infrastructure-config", headers=admin_headers)
    assert config_response.status_code == 200, config_response.text
    infrastructure = config_response.json()
    assert infrastructure["object_storage"]["secret_key"] == "********"
    assert infrastructure["graph_database"]["password"] == "********"

    reveal_response = await test_client.post(
        "/api/system/infrastructure-config/reveal",
        json={"section": "object_storage", "field": "secret_key"},
        headers=admin_headers,
    )
    assert reveal_response.status_code == 200, reveal_response.text
    assert reveal_response.json()["value"]
    assert reveal_response.json()["value"] != "********"

    for section in ("object_storage", "vector_database", "graph_database"):
        test_response = await test_client.post(
            "/api/system/infrastructure-config/test",
            json={"section": section, "values": infrastructure[section]},
            headers=admin_headers,
        )
        assert test_response.status_code == 200, test_response.text
        assert test_response.json()["status"] == "ok"


async def test_admin_can_fetch_tools_with_config_guide_field(test_client, admin_headers):
    response = await test_client.get("/api/system/tools", headers=admin_headers)
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)
    assert payload["data"]
    assert "config_guide" in payload["data"][0]
