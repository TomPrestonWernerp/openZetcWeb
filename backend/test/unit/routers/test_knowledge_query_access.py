from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.routers import knowledge_router
from server.utils.auth_middleware import get_db, get_required_user
from openzetc.storage.postgres.models_business import User


def _client(monkeypatch, *, accessible: bool) -> tuple[TestClient, list[tuple[str, str]], list[str]]:
    calls: list[tuple[str, str]] = []
    permission_calls: list[str] = []

    async def fake_required_user():
        return User(username="user", uid="user_1", password_hash="x", role="user", department_id=7)

    async def fake_db():
        return None

    async def fake_ensure_access(user, kb_id, db):
        assert user.uid == "user_1"
        assert kb_id == "kb_1"
        assert db is None
        if not accessible:
            raise HTTPException(status_code=403, detail="无权访问该知识库")
        return {"kb_id": kb_id}

    async def fake_require_permission(db, user, permission_code, **kwargs):
        assert db is None
        assert user.uid == "user_1"
        assert kwargs == {}
        permission_calls.append(permission_code)

    async def fake_query(query, *, kb_id, **_meta):
        calls.append((kb_id, query))
        return {"answer": "matched"}

    app = FastAPI()
    app.include_router(knowledge_router.knowledge, prefix="/api")
    app.dependency_overrides[get_required_user] = fake_required_user
    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(knowledge_router, "ensure_knowledge_access", fake_ensure_access)
    monkeypatch.setattr(knowledge_router, "require_permission", fake_require_permission)
    monkeypatch.setattr(knowledge_router.knowledge_base, "aquery", fake_query)
    return TestClient(app), calls, permission_calls


def test_accessible_user_can_query_shared_knowledge_base(monkeypatch):
    client, calls, permission_calls = _client(monkeypatch, accessible=True)

    response = client.post(
        "/api/knowledge/databases/kb_1/query",
        json={"query": "deployment policy", "meta": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"result": {"answer": "matched"}, "status": "success"}
    assert calls == [("kb_1", "deployment policy")]
    assert permission_calls == ["knowledge.query"]


def test_user_cannot_query_knowledge_base_outside_acl(monkeypatch):
    client, calls, permission_calls = _client(monkeypatch, accessible=False)

    response = client.post(
        "/api/knowledge/databases/kb_1/query",
        json={"query": "deployment policy", "meta": {}},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "无权访问该知识库"
    assert calls == []
    assert permission_calls == []
