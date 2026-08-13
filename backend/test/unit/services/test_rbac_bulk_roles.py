from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.services.rbac_service import update_users_roles
from yuxi.storage.postgres.models_business import (
    Department,
    RBACPermission,
    RBACRole,
    RBACRolePermission,
    RBACUserRole,
    User,
)


@pytest.mark.asyncio
async def test_batch_role_update_rejects_removing_last_base_role(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            Department.__table__,
            User.__table__,
            RBACPermission.__table__,
            RBACRole.__table__,
            RBACRolePermission.__table__,
            RBACUserRole.__table__,
        ):
            await connection.run_sync(lambda sync_connection, table=table: table.create(sync_connection))

    async def allow(*args, **kwargs):
        return "global"

    async def actor_permissions(*args, **kwargs):
        return {"user.assign_role": "global", "role.assign": "global"}

    monkeypatch.setattr("yuxi.services.rbac_service.require_permission", allow)
    monkeypatch.setattr("yuxi.services.rbac_service.get_user_permission_map", actor_permissions)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        department = Department(name="信息部")
        db.add(department)
        await db.flush()
        target = User(
            uid="member001",
            username="成员甲",
            password_hash="hash",
            role="user",
            department_id=department.id,
        )
        member_role = RBACRole(code="system.member", name="普通用户", is_system=True)
        db.add_all([target, member_role])
        await db.flush()
        db.add(RBACUserRole(user_id=target.id, role_id=member_role.id))
        await db.commit()

        actor = SimpleNamespace(id=999, uid="admin", role="superadmin", department_id=department.id)
        with pytest.raises(HTTPException, match="至少需要保留一个系统基础角色"):
            await update_users_roles(db, actor, [target], [member_role.id], "remove")
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_role_update_rejects_cross_department_role(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            Department.__table__,
            User.__table__,
            RBACPermission.__table__,
            RBACRole.__table__,
            RBACRolePermission.__table__,
            RBACUserRole.__table__,
        ):
            await connection.run_sync(lambda sync_connection, table=table: table.create(sync_connection))

    async def allow(*args, **kwargs):
        return "global"

    async def actor_permissions(*args, **kwargs):
        return {"user.assign_role": "global", "role.assign": "global"}

    monkeypatch.setattr("yuxi.services.rbac_service.require_permission", allow)
    monkeypatch.setattr("yuxi.services.rbac_service.get_user_permission_map", actor_permissions)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        own_department = Department(name="信息部")
        other_department = Department(name="财务部")
        db.add_all([own_department, other_department])
        await db.flush()
        target = User(
            uid="member002",
            username="成员乙",
            password_hash="hash",
            role="user",
            department_id=own_department.id,
        )
        member_role = RBACRole(code="system.member", name="普通用户", is_system=True)
        other_role = RBACRole(
            code="finance.auditor",
            name="财务审核员",
            department_id=other_department.id,
        )
        db.add_all([target, member_role, other_role])
        await db.flush()
        db.add(RBACUserRole(user_id=target.id, role_id=member_role.id))
        await db.commit()

        actor = SimpleNamespace(id=999, uid="admin", role="superadmin", department_id=own_department.id)
        with pytest.raises(HTTPException, match="不能分配其他部门的角色"):
            await update_users_roles(db, actor, [target], [member_role.id, other_role.id], "replace")
    await engine.dispose()
