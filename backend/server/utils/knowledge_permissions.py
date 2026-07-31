"""FastAPI 知识库资源权限依赖。"""

from fastapi import Depends, HTTPException, Request, status

from server.utils.auth_middleware import get_required_user
from yuxi.knowledge.runtime import knowledge_base
from yuxi.services.knowledge_permission_service import (
    can_manage_database,
    get_user_knowledge_permissions,
)
from yuxi.storage.postgres.models_business import User


async def ensure_knowledge_access(user: User, kb_id: str) -> dict:
    database = await knowledge_base.get_database_info(kb_id)
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if not await knowledge_base.check_accessible(user.to_dict(), kb_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")
    return database


async def ensure_knowledge_manage(user: User, kb_id: str) -> dict:
    database = await ensure_knowledge_access(user, kb_id)
    permissions = await get_user_knowledge_permissions(user)
    if not can_manage_database(user, database, permissions):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该知识库为只读共享资源")
    return database


async def get_knowledge_access_user(
    request: Request,
    current_user: User = Depends(get_required_user),
) -> User:
    kb_id = request.path_params.get("kb_id")
    if kb_id:
        await ensure_knowledge_access(current_user, kb_id)
    return current_user


async def get_knowledge_manage_user(
    request: Request,
    current_user: User = Depends(get_required_user),
) -> User:
    kb_id = request.path_params.get("kb_id")
    if not kb_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少知识库 ID")
    await ensure_knowledge_manage(current_user, kb_id)
    return current_user


async def get_knowledge_create_user(current_user: User = Depends(get_required_user)) -> User:
    permissions = await get_user_knowledge_permissions(current_user)
    if not permissions.get("create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色不允许创建知识库")
    return current_user
