"""统一 RBAC 权限目录、角色绑定与授权判断。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import (
    RBACPermission,
    RBACRole,
    RBACRolePermission,
    RBACUserRole,
    User,
)

VALID_SCOPES = ("own", "department", "global")
SCOPE_RANK = {"own": 1, "department": 2, "global": 3}


def _permission(domain: str, action: str, label: str, description: str) -> dict[str, str]:
    return {
        "code": f"{domain}.{action}",
        "domain": domain,
        "action": action,
        "label": label,
        "description": description,
    }


PERMISSION_DEFINITIONS = (
    _permission("user", "view", "查看人员", "查看授权范围内的人员资料。"),
    _permission("user", "create", "创建人员", "在授权范围内创建用户。"),
    _permission("user", "update", "编辑人员", "编辑授权范围内的用户资料。"),
    _permission("user", "delete", "删除人员", "停用或删除授权范围内的用户。"),
    _permission("user", "assign_role", "分配角色", "为授权范围内的用户分配角色。"),
    _permission("department", "view", "查看部门", "查看组织部门信息。"),
    _permission("department", "create", "创建部门", "创建新的组织部门。"),
    _permission("department", "update", "编辑部门", "编辑授权范围内的部门。"),
    _permission("department", "delete", "删除部门", "删除授权范围内的部门。"),
    _permission("role", "view", "查看角色", "查看角色及其权限。"),
    _permission("role", "create", "创建角色", "创建自定义角色。"),
    _permission("role", "update", "编辑角色", "编辑自定义角色及权限。"),
    _permission("role", "delete", "删除角色", "删除未使用的自定义角色。"),
    _permission("role", "assign", "分配角色", "将角色分配给用户。"),
    _permission("knowledge", "view", "查看知识库", "查看可访问的知识库。"),
    _permission("knowledge", "create", "创建知识库", "创建知识库。"),
    _permission("knowledge", "update", "编辑知识库", "编辑知识库配置和文件。"),
    _permission("knowledge", "delete", "删除知识库", "删除知识库。"),
    _permission("knowledge", "upload", "上传知识文件", "上传、移动和删除知识文件。"),
    _permission("knowledge", "index", "知识入库", "执行向量化、图谱构建和重新入库。"),
    _permission("knowledge", "query", "检索知识库", "调用向量、全文和图谱检索。"),
    _permission("knowledge", "share", "共享知识库", "调整知识库共享范围。"),
    _permission("agent", "view", "查看智能体", "查看可访问的智能体。"),
    _permission("agent", "create", "创建智能体", "创建智能体。"),
    _permission("agent", "update", "编辑智能体", "编辑智能体配置。"),
    _permission("agent", "delete", "删除智能体", "删除智能体。"),
    _permission("agent", "run", "运行智能体", "在对话和 API 中运行智能体。"),
    _permission("agent", "share", "共享智能体", "调整智能体共享范围。"),
    _permission("agent", "set_default", "设置默认智能体", "设置系统默认智能体。"),
    _permission("skill", "view", "查看 Skill", "查看可访问的 Skill。"),
    _permission("skill", "create", "创建 Skill", "创建或导入 Skill。"),
    _permission("skill", "update", "编辑 Skill", "编辑 Skill 内容和依赖。"),
    _permission("skill", "delete", "删除 Skill", "删除 Skill。"),
    _permission("skill", "install", "安装 Skill", "从市场或压缩包安装 Skill。"),
    _permission("skill", "enable", "启停 Skill", "启用或停用 Skill。"),
    _permission("skill", "share", "共享 Skill", "调整 Skill 共享范围。"),
    _permission("mcp", "view", "查看 MCP", "查看可访问的 MCP 服务。"),
    _permission("mcp", "create", "创建 MCP", "创建 MCP 服务配置。"),
    _permission("mcp", "update", "编辑 MCP", "编辑 MCP 服务和工具配置。"),
    _permission("mcp", "delete", "删除 MCP", "删除 MCP 服务。"),
    _permission("mcp", "use", "使用 MCP", "允许智能体调用 MCP 工具。"),
    _permission("mcp", "test", "测试 MCP", "测试连接并刷新工具列表。"),
    _permission("mcp", "enable", "启停 MCP", "启用或停用 MCP 服务和工具。"),
    _permission("mcp", "share", "共享 MCP", "调整 MCP 服务共享范围。"),
    _permission("resource_submission", "submit", "提交公共资源", "将本地 Agent、Skill 或 MCP 提交到部门审核队列。"),
    _permission("resource_submission", "review", "审核公共资源", "审核本部门用户提交的资源并决定是否公开。"),
)

PERMISSION_CODES = tuple(item["code"] for item in PERMISSION_DEFINITIONS)
RESOURCE_DOMAINS = ("knowledge", "agent", "skill", "mcp")

BUILTIN_ROLE_DEFINITIONS = {
    "superadmin": {
        "code": "system.superadmin",
        "name": "超级管理员",
        "description": "拥有全公司全部权限。",
    },
    "admin": {
        "code": "system.department_admin",
        "name": "部门管理员",
        "description": "管理本部门人员和业务资源。",
    },
    "user": {
        "code": "system.member",
        "name": "普通用户",
        "description": "使用共享资源并管理本人创建的资源。",
    },
}


def _domain_codes(domain: str) -> set[str]:
    return {code for code in PERMISSION_CODES if code.startswith(f"{domain}.")}


BUILTIN_ROLE_GRANTS: dict[str, dict[str, str]] = {
    "superadmin": {code: "global" for code in PERMISSION_CODES},
    "admin": {
        **{code: "department" for code in _domain_codes("user")},
        "department.view": "department",
        "role.view": "department",
        "role.create": "department",
        "role.update": "department",
        "role.delete": "department",
        "role.assign": "department",
        **{
            code: "department"
            for domain in RESOURCE_DOMAINS
            for code in _domain_codes(domain)
            if code != "agent.set_default"
        },
        "resource_submission.submit": "own",
        "resource_submission.review": "department",
    },
    "user": {
        "user.view": "own",
        "department.view": "department",
        "role.view": "own",
        "knowledge.view": "global",
        "knowledge.create": "own",
        "knowledge.update": "own",
        "knowledge.delete": "own",
        "knowledge.upload": "own",
        "knowledge.index": "own",
        "knowledge.query": "global",
        "knowledge.share": "own",
        "agent.view": "global",
        "agent.create": "own",
        "agent.update": "own",
        "agent.delete": "own",
        "agent.run": "global",
        "agent.share": "own",
        "skill.view": "global",
        "skill.create": "own",
        "skill.update": "own",
        "skill.delete": "own",
        "skill.install": "own",
        "skill.enable": "own",
        "skill.share": "own",
        "mcp.view": "global",
        "mcp.create": "own",
        "mcp.update": "own",
        "mcp.delete": "own",
        "mcp.use": "global",
        "mcp.test": "own",
        "mcp.enable": "own",
        "resource_submission.submit": "own",
    },
}


def strongest_scope(scopes: Iterable[str]) -> str | None:
    valid = [scope for scope in scopes if scope in SCOPE_RANK]
    return max(valid, key=SCOPE_RANK.get) if valid else None


def scope_allows(
    scope: str | None,
    user: User,
    *,
    owner_uid: str | None = None,
    department_id: int | None = None,
    target_user_id: int | None = None,
) -> bool:
    """判断某个权限范围是否覆盖目标对象。没有目标上下文时用于创建类操作。"""
    if scope not in SCOPE_RANK:
        return False
    if owner_uid is None and department_id is None and target_user_id is None:
        return True
    if scope == "global":
        return True
    if scope == "department":
        return department_id is not None and department_id == user.department_id
    return bool(
        (owner_uid is not None and owner_uid == user.uid)
        or (target_user_id is not None and target_user_id == user.id)
    )


async def ensure_rbac_seeded(db: AsyncSession) -> None:
    """幂等初始化权限目录、系统角色、角色权限和旧用户角色绑定。"""
    permission_result = await db.execute(select(RBACPermission))
    permissions = {item.code: item for item in permission_result.scalars().all()}
    for definition in PERMISSION_DEFINITIONS:
        item = permissions.get(definition["code"])
        if item is None:
            item = RBACPermission(**definition)
            db.add(item)
            permissions[definition["code"]] = item
        else:
            item.domain = definition["domain"]
            item.action = definition["action"]
            item.label = definition["label"]
            item.description = definition["description"]
    await db.flush()

    role_result = await db.execute(select(RBACRole).where(RBACRole.is_system.is_(True)))
    roles = {item.code: item for item in role_result.scalars().all()}
    roles_by_legacy: dict[str, RBACRole] = {}
    for legacy_role, definition in BUILTIN_ROLE_DEFINITIONS.items():
        role = roles.get(definition["code"])
        if role is None:
            role = RBACRole(**definition, is_system=True)
            db.add(role)
        else:
            role.name = definition["name"]
            role.description = definition["description"]
        roles_by_legacy[legacy_role] = role
    await db.flush()

    for legacy_role, role in roles_by_legacy.items():
        await db.execute(delete(RBACRolePermission).where(RBACRolePermission.role_id == role.id))
        for code, scope in BUILTIN_ROLE_GRANTS[legacy_role].items():
            db.add(
                RBACRolePermission(
                    role_id=role.id,
                    permission_id=permissions[code].id,
                    scope=scope,
                )
            )
    await db.flush()

    user_result = await db.execute(select(User).where(User.is_deleted == 0))
    for user in user_result.scalars().all():
        legacy_role = user.role if user.role in roles_by_legacy else "user"
        role = roles_by_legacy[legacy_role]
        binding_result = await db.execute(
            select(RBACUserRole).where(
                RBACUserRole.user_id == user.id,
                RBACUserRole.role_id == role.id,
            )
        )
        if binding_result.scalar_one_or_none() is None:
            db.add(RBACUserRole(user_id=user.id, role_id=role.id))
    await db.commit()


async def sync_user_system_role(
    db: AsyncSession,
    user: User,
    legacy_role: str | None = None,
    *,
    assigned_by_user_id: int | None = None,
) -> None:
    """同步旧 `User.role` 与一个内置系统角色，同时保留自定义角色。"""
    role_name = legacy_role if legacy_role in BUILTIN_ROLE_DEFINITIONS else "user"
    system_codes = [item["code"] for item in BUILTIN_ROLE_DEFINITIONS.values()]
    role_result = await db.execute(select(RBACRole).where(RBACRole.code.in_(system_codes)))
    system_roles = {role.code: role for role in role_result.scalars().all()}
    desired = system_roles.get(BUILTIN_ROLE_DEFINITIONS[role_name]["code"])
    if desired is None:
        await ensure_rbac_seeded(db)
        role_result = await db.execute(select(RBACRole).where(RBACRole.code.in_(system_codes)))
        system_roles = {role.code: role for role in role_result.scalars().all()}
        desired = system_roles[BUILTIN_ROLE_DEFINITIONS[role_name]["code"]]

    await db.execute(
        delete(RBACUserRole).where(
            RBACUserRole.user_id == user.id,
            RBACUserRole.role_id.in_([role.id for role in system_roles.values()]),
        )
    )
    db.add(
        RBACUserRole(
            user_id=user.id,
            role_id=desired.id,
            assigned_by_user_id=assigned_by_user_id,
        )
    )
    user.role = role_name
    await db.flush()


async def get_user_permission_map(db: AsyncSession, user: User) -> dict[str, str]:
    if user.role == "superadmin":
        return BUILTIN_ROLE_GRANTS["superadmin"].copy()
    if db is None:
        # 部分离线/安装流程和历史单元测试没有数据库会话。旧版 admin
        # 没有部门资源边界，因此仅在这个无数据库兼容路径中保留全局管理语义；
        # 正常请求始终通过数据库中的 RBAC 角色和 scope 判定。
        grants = BUILTIN_ROLE_GRANTS.get(user.role, BUILTIN_ROLE_GRANTS["user"]).copy()
        if user.role == "admin":
            return {code: "global" for code in grants}
        return grants
    result = await db.execute(
        select(RBACPermission.code, RBACRolePermission.scope)
        .join(RBACRolePermission, RBACRolePermission.permission_id == RBACPermission.id)
        .join(RBACUserRole, RBACUserRole.role_id == RBACRolePermission.role_id)
        .where(RBACUserRole.user_id == user.id)
    )
    merged: dict[str, str] = {}
    for code, scope in result.all():
        current = merged.get(code)
        if current is None or SCOPE_RANK.get(scope, 0) > SCOPE_RANK.get(current, 0):
            merged[code] = scope
    if not merged:
        return BUILTIN_ROLE_GRANTS.get(user.role, BUILTIN_ROLE_GRANTS["user"]).copy()
    return merged


async def get_user_roles(db: AsyncSession, user_id: int) -> list[RBACRole]:
    result = await db.execute(
        select(RBACRole)
        .join(RBACUserRole, RBACUserRole.role_id == RBACRole.id)
        .where(RBACUserRole.user_id == user_id)
        .order_by(RBACRole.is_system.desc(), RBACRole.name.asc())
    )
    return list(result.scalars().all())


async def update_users_roles(
    db: AsyncSession,
    current_user: User,
    targets: list[User],
    role_ids: list[int],
    mode: Literal["add", "remove", "replace"] = "replace",
) -> dict[int, list[RBACRole]]:
    """Validate and stage role changes for one or more users without committing.

    The caller owns the transaction. All targets are validated before any binding is
    changed, so a failed batch never leaves a partially updated role assignment.
    """
    if not targets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一名用户")
    unique_role_ids = list(dict.fromkeys(role_ids))
    if not unique_role_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一个角色")

    await db.execute(select(User.id).where(User.id.in_([target.id for target in targets])).with_for_update())
    role_result = await db.execute(select(RBACRole).where(RBACRole.id.in_(unique_role_ids)))
    requested_roles = list(role_result.scalars().all())
    if len(requested_roles) != len(unique_role_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="包含不存在的角色")
    requested_by_id = {role.id: role for role in requested_roles}

    target_ids = [target.id for target in targets]
    current_result = await db.execute(
        select(RBACUserRole.user_id, RBACRole)
        .join(RBACRole, RBACRole.id == RBACUserRole.role_id)
        .where(RBACUserRole.user_id.in_(target_ids))
    )
    current_by_user: dict[int, dict[int, RBACRole]] = {target_id: {} for target_id in target_ids}
    for target_id, role in current_result.all():
        current_by_user[target_id][role.id] = role

    actor_permissions = await get_user_permission_map(db, current_user)
    permission_result = await db.execute(
        select(RBACRolePermission.role_id, RBACPermission.code, RBACRolePermission.scope)
        .join(RBACPermission, RBACPermission.id == RBACRolePermission.permission_id)
        .where(RBACRolePermission.role_id.in_(unique_role_ids))
    )
    grants_by_role: dict[int, dict[str, str]] = {role_id: {} for role_id in unique_role_ids}
    for role_id, code, scope in permission_result.all():
        grants_by_role[role_id][code] = scope

    system_codes = {item["code"]: legacy for legacy, item in BUILTIN_ROLE_DEFINITIONS.items()}
    resulting: dict[int, dict[int, RBACRole]] = {}
    for target in targets:
        await require_permission(
            db,
            current_user,
            "user.assign_role",
            department_id=target.department_id,
            target_user_id=target.id,
        )
        await require_permission(
            db,
            current_user,
            "role.assign",
            department_id=target.department_id,
            target_user_id=target.id,
        )
        if target.role == "superadmin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="超级管理员角色不可修改")
        if target.id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能修改自己的角色")

        current = current_by_user[target.id]
        if mode == "add":
            candidate = {**current, **requested_by_id}
        elif mode == "remove":
            candidate = {role_id: role for role_id, role in current.items() if role_id not in requested_by_id}
        else:
            candidate = requested_by_id.copy()

        for role in candidate.values():
            if role.department_id is not None and role.department_id != target.department_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能分配其他部门的角色")

        added_ids = set(candidate) - set(current)
        for role_id in added_ids:
            role = candidate[role_id]
            if role.department_id is None and not role.is_system:
                assignment_scope = await require_permission(db, current_user, "role.assign")
                if assignment_scope != "global":
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能分配公司级自定义角色")

        for role_id in added_ids:
            added_role = requested_by_id[role_id]
            if added_role.is_system:
                legacy_role = system_codes.get(added_role.code)
                if legacy_role == "superadmin" or (
                    legacy_role == "admin" and current_user.role != "superadmin"
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"不能分配系统角色：{added_role.name}",
                    )
                # Department administrators are explicitly allowed to assign the
                # built-in member role even though some read permissions are global.
                continue
            exceeded = [
                code
                for code, scope in grants_by_role.get(role_id, {}).items()
                if SCOPE_RANK.get(actor_permissions.get(code), 0) < SCOPE_RANK.get(scope, 0)
            ]
            if exceeded:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"不能分配超出自身权限的角色：{requested_by_id[role_id].name}",
                )

        base_roles = [role for role in candidate.values() if role.code in system_codes]
        if not base_roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每名用户至少需要保留一个系统基础角色")
        if len(base_roles) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每名用户只能分配一个系统基础角色")
        if base_roles[0].code == BUILTIN_ROLE_DEFINITIONS["superadmin"]["code"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="超级管理员角色不可通过授权接口分配")
        resulting[target.id] = candidate

    affected_departments = {
        int(target.department_id)
        for target in targets
        if target.department_id is not None and target.role == "admin"
    }
    if affected_departments:
        count_result = await db.execute(
            select(User.department_id, func.count(User.id))
            .where(
                User.department_id.in_(affected_departments),
                User.role == "admin",
                User.is_deleted == 0,
            )
            .group_by(User.department_id)
        )
        admin_counts = {int(department_id): count for department_id, count in count_result.all()}
        for department_id in affected_departments:
            removed = sum(
                1
                for target in targets
                if target.department_id == department_id
                and target.role == "admin"
                and system_codes[next(role.code for role in resulting[target.id].values() if role.code in system_codes)]
                != "admin"
            )
            if admin_counts.get(department_id, 0) - removed < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不能移除部门唯一管理员的管理员角色",
                )

    for target in targets:
        current = current_by_user[target.id]
        candidate = resulting[target.id]
        removed_ids = set(current) - set(candidate)
        if removed_ids:
            await db.execute(
                delete(RBACUserRole).where(
                    RBACUserRole.user_id == target.id,
                    RBACUserRole.role_id.in_(removed_ids),
                )
            )
        for role_id in set(candidate) - set(current):
            db.add(
                RBACUserRole(
                    user_id=target.id,
                    role_id=role_id,
                    assigned_by_user_id=current_user.id,
                )
            )
        base_role = next(role for role in candidate.values() if role.code in system_codes)
        target.role = system_codes[base_role.code]
    await db.flush()
    return {user_id: list(roles.values()) for user_id, roles in resulting.items()}


async def has_permission(
    db: AsyncSession,
    user: User,
    code: str,
    *,
    owner_uid: str | None = None,
    department_id: int | None = None,
    target_user_id: int | None = None,
) -> bool:
    permission_map = await get_user_permission_map(db, user)
    return scope_allows(
        permission_map.get(code),
        user,
        owner_uid=owner_uid,
        department_id=department_id,
        target_user_id=target_user_id,
    )


async def require_permission(
    db: AsyncSession,
    user: User,
    code: str,
    *,
    owner_uid: str | None = None,
    department_id: int | None = None,
    target_user_id: int | None = None,
) -> str:
    permission_map = await get_user_permission_map(db, user)
    scope = permission_map.get(code)
    if not scope_allows(
        scope,
        user,
        owner_uid=owner_uid,
        department_id=department_id,
        target_user_id=target_user_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少权限：{code}",
        )
    return scope


async def validate_share_config(
    db: AsyncSession,
    user: User,
    permission_code: str,
    share_config: dict[str, Any] | None,
    *,
    owner_uid: str | None = None,
    department_id: int | None = None,
) -> dict[str, Any]:
    """校验资源共享范围不超过操作者的授权作用域。"""
    scope = await require_permission(
        db,
        user,
        permission_code,
        owner_uid=owner_uid,
        department_id=department_id,
    )
    config = dict(share_config or {})
    access_level = config.get("access_level") or "user"
    department_ids = [int(value) for value in config.get("department_ids") or []]
    user_uids = [str(value) for value in config.get("user_uids") or []]

    if access_level == "global" and scope != "global":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前权限不能共享到全公司")
    if access_level == "department" and scope == "own":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前权限不能共享到部门")
    if access_level == "department" and scope == "department":
        if not user.department_id or set(department_ids or [user.department_id]) != {int(user.department_id)}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能共享到本人所在部门")
    if access_level == "user" and scope == "own":
        if set(user_uids or [str(user.uid)]) != {str(user.uid)}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能保留为本人私有资源")
    if access_level == "user" and scope == "department" and user_uids:
        result = await db.execute(select(User.uid, User.department_id).where(User.uid.in_(user_uids)))
        rows = result.all()
        if len(rows) != len(set(user_uids)) or any(row.department_id != user.department_id for row in rows):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能共享给本部门用户")
    return {
        **config,
        "access_level": access_level,
        "department_ids": department_ids,
        "user_uids": user_uids,
    }


async def replace_role_permissions(
    db: AsyncSession,
    role: RBACRole,
    grants: dict[str, str],
) -> None:
    invalid_scopes = {scope for scope in grants.values() if scope not in VALID_SCOPES}
    if invalid_scopes:
        raise ValueError(f"无效权限范围：{', '.join(sorted(invalid_scopes))}")
    permission_result = await db.execute(
        select(RBACPermission).where(RBACPermission.code.in_(list(grants.keys())))
    )
    permissions = {item.code: item for item in permission_result.scalars().all()}
    missing = set(grants) - set(permissions)
    if missing:
        raise ValueError(f"未知权限：{', '.join(sorted(missing))}")
    await db.execute(delete(RBACRolePermission).where(RBACRolePermission.role_id == role.id))
    for code, scope in grants.items():
        db.add(
            RBACRolePermission(
                role_id=role.id,
                permission_id=permissions[code].id,
                scope=scope,
            )
        )
    await db.flush()


def generate_role_code() -> str:
    return f"custom.{uuid4().hex[:16]}"


async def serialize_role(db: AsyncSession, role: RBACRole) -> dict[str, Any]:
    result = await db.execute(
        select(RBACPermission.code, RBACRolePermission.scope)
        .join(RBACRolePermission, RBACRolePermission.permission_id == RBACPermission.id)
        .where(RBACRolePermission.role_id == role.id)
        .order_by(RBACPermission.domain.asc(), RBACPermission.action.asc())
    )
    return {**role.to_dict(), "permissions": {code: scope for code, scope in result.all()}}
