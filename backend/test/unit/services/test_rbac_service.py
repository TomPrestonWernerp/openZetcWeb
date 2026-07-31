from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.services.rbac_service import (
    BUILTIN_ROLE_GRANTS,
    PERMISSION_CODES,
    scope_allows,
    strongest_scope,
    validate_share_config,
)


def make_user(**overrides):
    values = {"id": 11, "uid": "u-11", "role": "user", "department_id": 7}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_permission_catalog_is_unique_and_covers_all_managed_resources():
    assert len(PERMISSION_CODES) == len(set(PERMISSION_CODES))
    for domain in ("user", "department", "role", "knowledge", "agent", "skill", "mcp"):
        assert any(code.startswith(f"{domain}.") for code in PERMISSION_CODES)


def test_builtin_roles_have_expected_scope_boundaries():
    assert BUILTIN_ROLE_GRANTS["superadmin"]["mcp.delete"] == "global"
    assert BUILTIN_ROLE_GRANTS["admin"]["skill.update"] == "department"
    assert BUILTIN_ROLE_GRANTS["user"]["knowledge.update"] == "own"
    assert "user.assign_role" not in BUILTIN_ROLE_GRANTS["user"]


def test_scope_resolution_and_target_matching():
    user = make_user()
    assert strongest_scope(["own", "global", "department"]) == "global"
    assert scope_allows("own", user, owner_uid="u-11")
    assert not scope_allows("own", user, owner_uid="someone-else")
    assert scope_allows("department", user, department_id=7)
    assert not scope_allows("department", user, department_id=8)
    assert scope_allows("global", user, department_id=8)


@pytest.mark.asyncio
async def test_own_share_permission_cannot_publish_global(monkeypatch):
    async def fake_require_permission(*args, **kwargs):
        return "own"

    monkeypatch.setattr("yuxi.services.rbac_service.require_permission", fake_require_permission)
    with pytest.raises(HTTPException, match="不能共享到全公司"):
        await validate_share_config(
            SimpleNamespace(),
            make_user(),
            "knowledge.share",
            {"access_level": "global"},
        )


@pytest.mark.asyncio
async def test_department_share_is_restricted_to_current_department(monkeypatch):
    async def fake_require_permission(*args, **kwargs):
        return "department"

    monkeypatch.setattr("yuxi.services.rbac_service.require_permission", fake_require_permission)
    result = await validate_share_config(
        SimpleNamespace(),
        make_user(),
        "agent.share",
        {"access_level": "department", "department_ids": [7]},
    )
    assert result["department_ids"] == [7]

    with pytest.raises(HTTPException, match="本人所在部门"):
        await validate_share_config(
            SimpleNamespace(),
            make_user(),
            "agent.share",
            {"access_level": "department", "department_ids": [8]},
        )
