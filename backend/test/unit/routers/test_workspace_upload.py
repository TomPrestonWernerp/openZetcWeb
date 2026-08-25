from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routers import workspace_router
from server.routers.workspace_router import workspace
from server.utils.auth_middleware import get_required_user
from openzetc.storage.postgres.models_business import User


def test_workspace_upload_forwards_relative_paths(monkeypatch) -> None:
    captured = {}

    async def fake_required_user():
        return User(username="user", uid="user", password_hash="x", role="user", department_id=1)

    async def fake_upload_workspace_files(**kwargs):
        captured.update(kwargs)
        return {"success": True, "entries": []}

    app = FastAPI()
    app.include_router(workspace, prefix="/api")
    app.dependency_overrides[get_required_user] = fake_required_user
    monkeypatch.setattr(workspace_router, "upload_workspace_files", fake_upload_workspace_files)
    client = TestClient(app)

    response = client.post(
        "/api/workspace/upload",
        data={
            "parent_path": "/国家标准/",
            "relative_paths": ["政策法规/国家/law.txt", "政策法规/地方/rule.txt"],
        },
        files=[
            ("files", ("law.txt", b"law", "text/plain")),
            ("files", ("rule.txt", b"rule", "text/plain")),
        ],
    )

    assert response.status_code == 200, response.text
    assert captured["parent_path"] == "/国家标准/"
    assert captured["relative_paths"] == ["政策法规/国家/law.txt", "政策法规/地方/rule.txt"]
    assert [file.filename for file in captured["files"]] == ["law.txt", "rule.txt"]
