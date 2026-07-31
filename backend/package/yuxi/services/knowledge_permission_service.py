"""部门角色与知识库资源权限。

角色策略按部门持久化。超级管理员始终拥有完整权限；部门管理员只能
配置本部门普通用户的策略，避免跨部门提权。
"""

from __future__ import annotations

from typing import Any

from yuxi.repositories.department_repository import DepartmentRepository
from yuxi.storage.postgres.models_business import User

KNOWLEDGE_PERMISSION_KEYS = (
    "create",
    "manage_own",
    "manage_department",
    "manage_all",
    "share_users",
    "share_department",
    "share_global",
)

DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "user": {
        "create": True,
        "manage_own": True,
        "manage_department": False,
        "manage_all": False,
        "share_users": False,
        "share_department": False,
        "share_global": False,
    },
    "admin": {
        "create": True,
        "manage_own": True,
        "manage_department": True,
        "manage_all": False,
        "share_users": True,
        "share_department": True,
        "share_global": True,
    },
    "superadmin": {key: True for key in KNOWLEDGE_PERMISSION_KEYS},
}


def normalize_permission_policy(role: str, policy: dict[str, Any] | None = None) -> dict[str, bool]:
    """将持久化策略与安全默认值合并，只接受已知布尔字段。"""
    normalized = dict(DEFAULT_ROLE_PERMISSIONS.get(role, DEFAULT_ROLE_PERMISSIONS["user"]))
    if isinstance(policy, dict):
        for key in KNOWLEDGE_PERMISSION_KEYS:
            if key in policy:
                normalized[key] = bool(policy[key])
    return normalized


def normalize_department_role_permissions(value: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    value = value if isinstance(value, dict) else {}
    return {
        "admin": normalize_permission_policy("admin", value.get("admin")),
        "user": normalize_permission_policy("user", value.get("user")),
    }


async def get_user_knowledge_permissions(user: User | dict[str, Any]) -> dict[str, bool]:
    role = user.get("role") if isinstance(user, dict) else user.role
    if role == "superadmin":
        return dict(DEFAULT_ROLE_PERMISSIONS["superadmin"])

    department_id = user.get("department_id") if isinstance(user, dict) else user.department_id
    if department_id is None:
        return normalize_permission_policy(role)

    department = await DepartmentRepository().get_by_id(int(department_id))
    stored = department.role_permissions if department else {}
    return normalize_permission_policy(role, (stored or {}).get(role))


def allowed_share_levels(permissions: dict[str, bool]) -> list[str]:
    """个人级共享始终可用于创建私有库，其他范围按角色策略开放。"""
    levels = []
    if permissions.get("share_global"):
        levels.append("global")
    if permissions.get("share_department"):
        levels.append("department")
    levels.append("user")
    return levels


def normalize_share_config_for_user(
    share_config: dict[str, Any] | None,
    *,
    user: User,
    permissions: dict[str, bool],
) -> dict[str, Any]:
    """按角色策略收窄共享范围，防止绕过前端提交越权配置。"""
    requested = share_config if isinstance(share_config, dict) else {}
    access_level = str(requested.get("access_level") or "user")
    permitted_levels = allowed_share_levels(permissions)
    if access_level not in permitted_levels:
        raise PermissionError(f"当前角色不能创建或修改为 {access_level} 共享知识库")

    if access_level == "global":
        return {"access_level": "global", "department_ids": [], "user_uids": []}

    if access_level == "department":
        department_ids = []
        for value in requested.get("department_ids") or []:
            try:
                department_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if user.role != "superadmin":
            if user.department_id is None:
                raise PermissionError("当前用户未分配部门，不能创建部门知识库")
            department_ids = [int(user.department_id)]
        if not department_ids:
            raise ValueError("请选择共享部门")
        return {"access_level": "department", "department_ids": sorted(set(department_ids)), "user_uids": []}

    requested_uids = [str(uid) for uid in (requested.get("user_uids") or []) if str(uid).strip()]
    if not permissions.get("share_users"):
        requested_uids = [user.uid]
    elif user.uid not in requested_uids:
        requested_uids.append(user.uid)
    return {"access_level": "user", "department_ids": [], "user_uids": sorted(set(requested_uids))}


def can_manage_database(
    user: User | dict[str, Any],
    database: dict[str, Any],
    permissions: dict[str, bool],
) -> bool:
    role = user.get("role") if isinstance(user, dict) else user.role
    uid = str(user.get("uid") if isinstance(user, dict) else user.uid)
    department_id = user.get("department_id") if isinstance(user, dict) else user.department_id

    if role == "superadmin" or permissions.get("manage_all"):
        return True
    if permissions.get("manage_own") and str(database.get("created_by") or "") == uid:
        return True
    if not permissions.get("manage_department") or department_id is None:
        return False

    share_config = database.get("share_config") or {}
    if share_config.get("access_level") != "department":
        return False
    try:
        department_ids = {int(value) for value in (share_config.get("department_ids") or [])}
        return int(department_id) in department_ids
    except (TypeError, ValueError):
        return False


def database_access_summary(
    user: User | dict[str, Any],
    database: dict[str, Any],
    permissions: dict[str, bool],
) -> dict[str, bool]:
    uid = str(user.get("uid") if isinstance(user, dict) else user.uid)
    return {
        "can_view": True,
        "can_manage": can_manage_database(user, database, permissions),
        "is_owner": str(database.get("created_by") or "") == uid,
    }
