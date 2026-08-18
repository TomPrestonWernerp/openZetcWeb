from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.utils import knowledge_permissions
from yuxi.storage.postgres.models_business import User


pytestmark = pytest.mark.asyncio


def _user(*, role: str = "admin", department_id: int = 2) -> User:
    return User(
        username="department manager",
        uid="manager_2",
        password_hash="x",
        role=role,
        department_id=department_id,
    )


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
            "path_params": {"kb_id": "kb_shared"},
        }
    )


async def test_shared_database_view_uses_share_config_as_resource_boundary(monkeypatch):
    user = _user()
    calls: list[tuple[str, dict]] = []

    async def fake_database_info(kb_id):
        assert kb_id == "kb_shared"
        return {"kb_id": kb_id, "created_by": "other_user", "department_id": 1}

    async def fake_check_accessible(user_dict, kb_id):
        assert user_dict["uid"] == user.uid
        assert kb_id == "kb_shared"
        return True

    async def fake_has_permission(db, current_user, permission_code, **kwargs):
        assert db is session
        assert current_user is user
        calls.append((permission_code, kwargs))
        return permission_code == "knowledge.view"

    session = object()
    monkeypatch.setattr(knowledge_permissions.knowledge_base, "get_database_info", fake_database_info)
    monkeypatch.setattr(knowledge_permissions.knowledge_base, "check_accessible", fake_check_accessible)
    monkeypatch.setattr(knowledge_permissions, "has_permission", fake_has_permission)

    database = await knowledge_permissions.ensure_knowledge_access(user, "kb_shared", session)

    assert database["kb_id"] == "kb_shared"
    assert calls == [
        ("knowledge.view", {}),
        ("knowledge.update", {"owner_uid": "other_user", "department_id": 1}),
    ]


async def test_department_manager_can_open_private_database_in_own_department(monkeypatch):
    user = _user()

    async def fake_database_info(_kb_id):
        return {"kb_id": "kb_private", "created_by": "department_user", "department_id": 2}

    async def fake_check_accessible(_user_dict, _kb_id):
        return False

    async def fake_has_permission(_db, _user, permission_code, **kwargs):
        if permission_code == "knowledge.view":
            return False
        assert kwargs == {"owner_uid": "department_user", "department_id": 2}
        return True

    monkeypatch.setattr(knowledge_permissions.knowledge_base, "get_database_info", fake_database_info)
    monkeypatch.setattr(knowledge_permissions.knowledge_base, "check_accessible", fake_check_accessible)
    monkeypatch.setattr(knowledge_permissions, "has_permission", fake_has_permission)

    database = await knowledge_permissions.ensure_knowledge_access(user, "kb_private", object())

    assert database["kb_id"] == "kb_private"


async def test_inaccessible_database_is_rejected(monkeypatch):
    user = _user()

    async def fake_database_info(_kb_id):
        return {"kb_id": "kb_private", "created_by": "other_user", "department_id": 1}

    async def fake_check_accessible(_user_dict, _kb_id):
        return False

    async def fake_has_permission(*_args, **_kwargs):
        return False

    monkeypatch.setattr(knowledge_permissions.knowledge_base, "get_database_info", fake_database_info)
    monkeypatch.setattr(knowledge_permissions.knowledge_base, "check_accessible", fake_check_accessible)
    monkeypatch.setattr(knowledge_permissions, "has_permission", fake_has_permission)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge_permissions.ensure_knowledge_access(user, "kb_private", object())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "无权访问该知识库"


@pytest.mark.parametrize(
    "path",
    ["/api/knowledge/databases/kb_shared/query-params", "/api/knowledge/databases/kb_shared"],
)
async def test_read_endpoints_do_not_require_query_permission(monkeypatch, path):
    user = _user()
    query_permission_calls: list[str] = []

    async def fake_ensure_access(current_user, kb_id, db):
        assert current_user is user
        assert kb_id == "kb_shared"
        assert db is session
        return {"kb_id": kb_id}

    async def fake_require_permission(_db, _user, permission_code, **_kwargs):
        query_permission_calls.append(permission_code)

    session = object()
    monkeypatch.setattr(knowledge_permissions, "ensure_knowledge_access", fake_ensure_access)
    monkeypatch.setattr(knowledge_permissions, "require_permission", fake_require_permission)

    result = await knowledge_permissions.get_knowledge_access_user(_request(path), user, session)

    assert result is user
    assert query_permission_calls == []


@pytest.mark.parametrize(
    "path",
    ["/api/knowledge/databases/kb_shared/query", "/api/knowledge/databases/kb_shared/query-test"],
)
async def test_query_endpoints_require_query_permission(monkeypatch, path):
    user = _user()
    query_permission_calls: list[str] = []

    async def fake_ensure_access(_current_user, _kb_id, _db):
        return {"kb_id": "kb_shared"}

    async def fake_require_permission(db, current_user, permission_code, **kwargs):
        assert db is session
        assert current_user is user
        assert kwargs == {}
        query_permission_calls.append(permission_code)

    session = object()
    monkeypatch.setattr(knowledge_permissions, "ensure_knowledge_access", fake_ensure_access)
    monkeypatch.setattr(knowledge_permissions, "require_permission", fake_require_permission)

    await knowledge_permissions.get_knowledge_access_user(_request(path), user, session)

    assert query_permission_calls == ["knowledge.query"]
