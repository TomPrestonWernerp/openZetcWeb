from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routers import knowledge_router
from server.utils.auth_middleware import get_required_user
from yuxi.storage.postgres.models_business import User


def _client(monkeypatch, *, accessible: bool) -> tuple[TestClient, list[tuple[str, str]]]:
    calls: list[tuple[str, str]] = []

    async def fake_required_user():
        return User(username="user", uid="user_1", password_hash="x", role="user", department_id=7)

    async def fake_check_accessible(user, kb_id):
        assert user == {"uid": "user_1", "role": "user", "department_id": 7}
        assert kb_id == "kb_1"
        return accessible

    async def fake_query(query, *, kb_id, **_meta):
        calls.append((kb_id, query))
        return {"answer": "matched"}

    app = FastAPI()
    app.include_router(knowledge_router.knowledge, prefix="/api")
    app.dependency_overrides[get_required_user] = fake_required_user
    monkeypatch.setattr(knowledge_router.knowledge_base, "check_accessible", fake_check_accessible)
    monkeypatch.setattr(knowledge_router.knowledge_base, "aquery", fake_query)
    return TestClient(app), calls


def test_accessible_user_can_query_shared_knowledge_base(monkeypatch):
    client, calls = _client(monkeypatch, accessible=True)

    response = client.post(
        "/api/knowledge/databases/kb_1/query",
        json={"query": "deployment policy", "meta": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"result": {"answer": "matched"}, "status": "success"}
    assert calls == [("kb_1", "deployment policy")]


def test_user_cannot_query_knowledge_base_outside_acl(monkeypatch):
    client, calls = _client(monkeypatch, accessible=False)

    response = client.post(
        "/api/knowledge/databases/kb_1/query",
        json={"query": "deployment policy", "meta": {}},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"
    assert calls == []
