"""统一角色与权限管理 API。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from openzetc.services.rbac_service import (
    SCOPE_RANK,
    get_user_permission_map,
    get_user_roles,
    generate_role_code,
    replace_role_permissions,
    require_permission,
    serialize_role,
    update_users_roles,
)
from openzetc.storage.postgres.models_business import (
    Department,
    RBACPermission,
    RBACRole,
    RBACUserRole,
    User,
)

rbac = APIRouter(prefix="/rbac", tags=["rbac"])
PermissionScope = Literal["own", "department", "global"]


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    department_id: int | None = None
    permissions: dict[str, PermissionScope] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permissions: dict[str, PermissionScope] | None = None


class UserRolesUpdate(BaseModel):
    role_ids: list[int] = Field(min_length=1)


class BatchUserRolesUpdate(UserRolesUpdate):
    user_ids: list[int] = Field(min_length=1)
    mode: Literal["add", "remove", "replace"] = "replace"


async def _get_role_or_404(db: AsyncSession, role_id: int) -> RBACRole:
    result = await db.execute(select(RBACRole).where(RBACRole.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return role


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


async def _ensure_grants_delegable(
    db: AsyncSession,
    current_user: User,
    grants: dict[str, PermissionScope],
) -> None:
    """Prevent role editors from granting permissions or scopes they do not hold."""
    actor_permissions = await get_user_permission_map(db, current_user)
    exceeded = [
        code
        for code, scope in grants.items()
        if SCOPE_RANK.get(actor_permissions.get(code), 0) < SCOPE_RANK.get(scope, 0)
    ]
    if exceeded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"不能授予超出自身范围的权限：{', '.join(sorted(exceeded))}",
        )


async def _require_role_permission(
    db: AsyncSession,
    current_user: User,
    code: str,
    role: RBACRole,
) -> None:
    if role.department_id is None and not role.is_system:
        scope = await require_permission(db, current_user, code)
        if scope != "global":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少全局权限：{code}")
        return
    await require_permission(
        db,
        current_user,
        code,
        department_id=role.department_id or current_user.department_id,
    )


@rbac.get("/me")
async def get_my_access(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    roles = await get_user_roles(db, current_user.id)
    return {
        "user_id": current_user.id,
        "uid": current_user.uid,
        "legacy_role": current_user.role,
        "department_id": current_user.department_id,
        "roles": [role.to_dict() for role in roles],
        "permissions": await get_user_permission_map(db, current_user),
    }


@rbac.get("/permissions")
async def list_permissions(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await require_permission(db, current_user, "role.view")
    result = await db.execute(
        select(RBACPermission).order_by(RBACPermission.domain.asc(), RBACPermission.action.asc())
    )
    return [item.to_dict() for item in result.scalars().all()]


@rbac.get("/roles")
async def list_roles(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await require_permission(db, current_user, "role.view")
    query = select(RBACRole)
    if scope == "department":
        query = query.where(
            (RBACRole.is_system.is_(True)) | (RBACRole.department_id == current_user.department_id)
        )
    elif scope == "own":
        query = query.join(RBACUserRole, RBACUserRole.role_id == RBACRole.id).where(
            RBACUserRole.user_id == current_user.id
        )
    result = await db.execute(query.order_by(RBACRole.is_system.desc(), RBACRole.name.asc()))
    return [await serialize_role(db, role) for role in result.scalars().unique().all()]


@rbac.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await require_permission(db, current_user, "role.create")
    department_id = data.department_id
    if scope == "department":
        department_id = current_user.department_id
    if department_id is not None:
        department_result = await db.execute(select(Department.id).where(Department.id == department_id))
        if department_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="部门不存在")
    duplicate = await db.execute(
        select(RBACRole.id).where(
            RBACRole.department_id == department_id,
            func.lower(RBACRole.name) == data.name.strip().lower(),
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该范围内已存在同名角色")
    role = RBACRole(
        code=generate_role_code(),
        name=data.name.strip(),
        description=data.description,
        department_id=department_id,
        created_by_user_id=current_user.id,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    try:
        await _ensure_grants_delegable(db, current_user, data.permissions)
        await replace_role_permissions(db, role, data.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(role)
    return await serialize_role(db, role)


@rbac.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    role = await _get_role_or_404(db, role_id)
    await _require_role_permission(db, current_user, "role.view", role)
    return await serialize_role(db, role)


@rbac.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    data: RoleUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    role = await _get_role_or_404(db, role_id)
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统内置角色不可修改")
    await _require_role_permission(db, current_user, "role.update", role)
    if data.name is not None:
        duplicate = await db.execute(
            select(RBACRole.id).where(
                RBACRole.id != role.id,
                RBACRole.department_id == role.department_id,
                func.lower(RBACRole.name) == data.name.strip().lower(),
            )
        )
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该范围内已存在同名角色")
        role.name = data.name.strip()
    if data.description is not None:
        role.description = data.description
    if data.permissions is not None:
        try:
            await _ensure_grants_delegable(db, current_user, data.permissions)
            await replace_role_permissions(db, role, data.permissions)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(role)
    return await serialize_role(db, role)


@rbac.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    role = await _get_role_or_404(db, role_id)
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统内置角色不可删除")
    await _require_role_permission(db, current_user, "role.delete", role)
    await db.delete(role)
    await db.commit()
    return {"success": True}


@rbac.put("/users/batch/roles")
async def update_batch_user_roles(
    data: BatchUserRolesUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    user_ids = list(dict.fromkeys(data.user_ids))
    result = await db.execute(select(User).where(User.id.in_(user_ids), User.is_deleted == 0))
    users_by_id = {user.id: user for user in result.scalars().all()}
    if len(users_by_id) != len(user_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="包含不存在的用户")
    targets = [users_by_id[user_id] for user_id in user_ids]
    roles_by_user = await update_users_roles(db, current_user, targets, data.role_ids, data.mode)
    await db.commit()
    return {
        "updated_count": len(targets),
        "user_ids": user_ids,
        "mode": data.mode,
        "users": [
            {
                "user_id": target.id,
                "roles": [await serialize_role(db, role) for role in roles_by_user[target.id]],
            }
            for target in targets
        ],
    }


@rbac.get("/users/{user_id}/roles")
async def list_user_roles(
    user_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _get_user_or_404(db, user_id)
    await require_permission(
        db,
        current_user,
        "user.view",
        department_id=target.department_id,
        target_user_id=target.id,
    )
    return [await serialize_role(db, role) for role in await get_user_roles(db, target.id)]


@rbac.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: int,
    data: UserRolesUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _get_user_or_404(db, user_id)
    roles = (await update_users_roles(db, current_user, [target], data.role_ids))[target.id]
    await db.commit()
    return [await serialize_role(db, role) for role in roles]
