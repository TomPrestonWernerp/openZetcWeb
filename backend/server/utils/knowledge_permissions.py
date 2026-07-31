"""FastAPI 知识库资源权限依赖。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.knowledge.runtime import knowledge_base
from yuxi.services.rbac_service import has_permission, require_permission
from yuxi.storage.postgres.models_business import User


async def ensure_knowledge_access(user: User, kb_id: str, db: AsyncSession | None = None) -> dict:
    database = await knowledge_base.get_database_info(kb_id)
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    share_accessible = await knowledge_base.check_accessible(user.to_dict(), kb_id)
    if db is None:
        from yuxi.storage.postgres.manager import pg_manager

        async with pg_manager.get_async_session_context() as session:
            can_view = share_accessible and await has_permission(
                session,
                user,
                "knowledge.view",
                owner_uid=database.get("created_by"),
                department_id=database.get("department_id"),
            )
            can_manage = await has_permission(
                session,
                user,
                "knowledge.update",
                owner_uid=database.get("created_by"),
                department_id=database.get("department_id"),
            )
            if not can_view and not can_manage:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")
    else:
        can_view = share_accessible and await has_permission(
            db,
            user,
            "knowledge.view",
            owner_uid=database.get("created_by"),
            department_id=database.get("department_id"),
        )
        can_manage = await has_permission(
            db,
            user,
            "knowledge.update",
            owner_uid=database.get("created_by"),
            department_id=database.get("department_id"),
        )
        if not can_view and not can_manage:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")
    return database


async def ensure_knowledge_manage(
    user: User,
    kb_id: str,
    db: AsyncSession | None = None,
    permission_code: str = "knowledge.update",
) -> dict:
    database = await knowledge_base.get_database_info(kb_id)
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if db is None:
        from yuxi.storage.postgres.manager import pg_manager

        async with pg_manager.get_async_session_context() as session:
            await require_permission(
                session,
                user,
                permission_code,
                owner_uid=database.get("created_by"),
                department_id=database.get("department_id"),
            )
    else:
        await require_permission(
            db,
            user,
            permission_code,
            owner_uid=database.get("created_by"),
            department_id=database.get("department_id"),
        )
    return database


async def get_knowledge_access_user(
    request: Request,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    kb_id = request.path_params.get("kb_id")
    if kb_id:
        permission_code = "knowledge.query" if "/query" in request.url.path else "knowledge.view"
        database = await ensure_knowledge_access(current_user, kb_id, db)
        if permission_code != "knowledge.view":
            await require_permission(
                db,
                current_user,
                permission_code,
                owner_uid=database.get("created_by"),
                department_id=database.get("department_id"),
            )
    return current_user


async def get_knowledge_manage_user(
    request: Request,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    kb_id = request.path_params.get("kb_id")
    if not kb_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少知识库 ID")
    path = request.url.path
    permission_code = "knowledge.update"
    if request.method == "DELETE" and path.rstrip("/").endswith(kb_id):
        permission_code = "knowledge.delete"
    elif "graph-build" in path or "index" in path or "parse" in path:
        permission_code = "knowledge.index"
    elif "/documents" in path or "/folders" in path:
        permission_code = "knowledge.upload"
    await ensure_knowledge_manage(current_user, kb_id, db, permission_code)
    return current_user


async def get_knowledge_create_user(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    await require_permission(db, current_user, "knowledge.create")
    return current_user
