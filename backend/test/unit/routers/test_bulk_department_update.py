from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.routers.auth_router import BatchUserDepartmentUpdate, update_users_department
from yuxi.storage.postgres.models_business import (
    Department,
    RBACRole,
    RBACUserRole,
    User,
)


@pytest.mark.asyncio
async def test_moving_users_removes_old_department_role_bindings(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Department.__table__.create(sync_connection)
        )
        await connection.run_sync(lambda sync_connection: User.__table__.create(sync_connection))
        await connection.run_sync(lambda sync_connection: RBACRole.__table__.create(sync_connection))
        await connection.run_sync(lambda sync_connection: RBACUserRole.__table__.create(sync_connection))

    async def allow(*args, **kwargs):
        return "global"

    async def no_log(*args, **kwargs):
        return None

    monkeypatch.setattr("server.routers.auth_router.require_permission", allow)
    monkeypatch.setattr("server.routers.auth_router.log_operation", no_log)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        source = Department(name="来源部门")
        destination = Department(name="目标部门")
        db.add_all([source, destination])
        await db.flush()
        actor = User(
            uid="superadmin",
            username="超级管理员",
            password_hash="hash",
            role="superadmin",
            department_id=source.id,
        )
        target = User(
            uid="member001",
            username="成员甲",
            password_hash="hash",
            role="user",
            department_id=source.id,
        )
        system_role = RBACRole(code="system.member", name="普通用户", is_system=True)
        source_role = RBACRole(code="source.auditor", name="来源审核员", department_id=source.id)
        company_role = RBACRole(code="company.reader", name="公司读者")
        db.add_all([actor, target, system_role, source_role, company_role])
        await db.flush()
        db.add_all(
            [
                RBACUserRole(user_id=target.id, role_id=system_role.id),
                RBACUserRole(user_id=target.id, role_id=source_role.id),
                RBACUserRole(user_id=target.id, role_id=company_role.id),
            ]
        )
        await db.commit()

        response = await update_users_department(
            BatchUserDepartmentUpdate(user_ids=[target.id], department_id=destination.id),
            SimpleNamespace(client=None),
            actor,
            db,
        )
        remaining = await db.execute(
            select(RBACRole.code)
            .join(RBACUserRole, RBACUserRole.role_id == RBACRole.id)
            .where(RBACUserRole.user_id == target.id)
        )
        assert set(remaining.scalars().all()) == {"system.member", "company.reader"}
        assert response["removed_role_binding_count"] == 1
        assert response["removed_role_bindings"][0]["role_name"] == "来源审核员"
        assert target.department_id == destination.id
    await engine.dispose()
