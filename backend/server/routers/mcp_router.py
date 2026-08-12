"""MCP 服务器管理路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.agents.mcp.service import (
    create_mcp_server,
    get_mcp_tools_stats,
    delete_mcp_server,
    get_all_mcp_servers,
    get_all_mcp_tools,
    get_mcp_server,
    set_server_enabled,
    toggle_tool_enabled,
    update_mcp_server,
)
from yuxi.storage.postgres.models_business import User
from yuxi.services.rbac_service import (
    get_user_permission_map,
    has_permission,
    require_permission,
    validate_share_config,
)
from yuxi.utils import logger
from server.utils.auth_middleware import get_db, get_required_user

mcp = APIRouter(prefix="/system/mcp-servers", tags=["mcp"])


# =============================================================================
# === DTOs ===
# =============================================================================


class CreateMcpServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., description="稳定标识")
    name: str = Field(..., description="展示名称")
    transport: str = Field(..., description="传输类型：sse/streamable_http/stdio")
    url: str | None = Field(None, description="服务器 URL（sse/streamable_http）")
    command: str | None = Field(None, description="命令（stdio）")
    args: list | None = Field(None, description="命令参数数组（stdio）")
    env: dict | None = Field(None, description="环境变量（stdio）")
    description: str | None = Field(None, description="描述")
    headers: dict | None = Field(None, description="HTTP 请求头")
    timeout: int | None = Field(None, description="HTTP 超时时间（秒）")
    sse_read_timeout: int | None = Field(None, description="SSE 读取超时（秒）")
    tags: list | None = Field(None, description="标签数组")
    icon: str | None = Field(None, description="图标（emoji）")
    share_config: dict | None = Field(None, description="共享范围")


class UpdateMcpServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, description="展示名称")
    transport: str | None = Field(None, description="传输类型")
    url: str | None = Field(None, description="服务器 URL")
    command: str | None = Field(None, description="命令（stdio）")
    args: list | None = Field(None, description="命令参数数组（stdio）")
    env: dict | None = Field(None, description="环境变量（stdio）")
    description: str | None = Field(None, description="描述")
    headers: dict | None = Field(None, description="HTTP 请求头")
    timeout: int | None = Field(None, description="HTTP 超时时间（秒）")
    sse_read_timeout: int | None = Field(None, description="SSE 读取超时（秒）")
    tags: list | None = Field(None, description="标签数组")
    icon: str | None = Field(None, description="图标（emoji）")
    share_config: dict | None = Field(None, description="共享范围")


class UpdateMcpServerStatusRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用")


# =============================================================================
# === Helpers ===
# =============================================================================


async def get_server_or_404(db: AsyncSession, slug: str):
    """Helper to get server or raise 404."""
    server = await get_mcp_server(db, slug)
    if not server:
        raise HTTPException(status_code=404, detail=f"服务器 '{slug}' 不存在")
    return server


def _is_mcp_visible(user: User, server) -> bool:
    if user.role == "superadmin" or getattr(server, "created_by_uid", None) == user.uid:
        return True
    share_config = getattr(server, "share_config", None) or {"access_level": "global"}
    access_level = share_config.get("access_level") or "global"
    if access_level == "global":
        return True
    if access_level == "department":
        try:
            return int(user.department_id or 0) in {
                int(value) for value in share_config.get("department_ids") or []
            }
        except (TypeError, ValueError):
            return False
    return user.uid in (share_config.get("user_uids") or [])


async def _require_mcp_permission(db: AsyncSession, user: User, server, code: str) -> None:
    if code in {"mcp.view", "mcp.use"} and not _is_mcp_visible(user, server):
        raise HTTPException(status_code=404, detail="MCP 服务不存在")
    await require_permission(
        db,
        user,
        code,
        owner_uid=getattr(server, "created_by_uid", None),
        department_id=getattr(server, "department_id", None),
    )


async def _serialize_mcp(db: AsyncSession, user: User, server) -> dict:
    data = server.to_dict()
    is_visible = _is_mcp_visible(user, server)
    access = {
        "can_view": is_visible
        and await has_permission(
            db,
            user,
            "mcp.view",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
        "can_update": await has_permission(
            db,
            user,
            "mcp.update",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
        "can_delete": await has_permission(
            db,
            user,
            "mcp.delete",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
        "can_use": is_visible
        and await has_permission(
            db,
            user,
            "mcp.use",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
        "can_test": await has_permission(
            db,
            user,
            "mcp.test",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
        "can_enable": await has_permission(
            db,
            user,
            "mcp.enable",
            owner_uid=getattr(server, "created_by_uid", None),
            department_id=getattr(server, "department_id", None),
        ),
    }
    if getattr(server, "created_by_uid", None) is None and user.role == "user":
        for key in ("can_update", "can_delete", "can_test", "can_enable"):
            access[key] = False
    if not access["can_update"]:
        # MCP 鉴权信息可能包含 API Key、Token 等敏感值。只允许具备编辑权限的用户读取。
        safe_fields = {
            "slug",
            "name",
            "description",
            "enabled",
            "icon",
            "tags",
            "transport",
            "created_by",
            "created_by_uid",
            "department_id",
            "share_config",
            "access",
        }
        data = {key: value for key, value in data.items() if key in safe_fields}
    data["access"] = access
    return data


# =============================================================================
# === MCP 服务器 CRUD ===
# =============================================================================


@mcp.get("")
async def get_mcp_servers(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有 MCP 服务器配置（普通用户仅获取脱敏的基础信息）"""
    try:
        data = []
        for server in await get_all_mcp_servers(db):
            serialized = await _serialize_mcp(db, current_user, server)
            if serialized["access"]["can_view"] or any(
                serialized["access"][code] for code in ("can_update", "can_delete", "can_enable")
            ):
                data.append(serialized)
        share_scope = (await get_user_permission_map(db, current_user)).get("mcp.share")
        allowed_access_levels = ["user"]
        if share_scope in {"department", "global"}:
            allowed_access_levels.insert(0, "department")
        if share_scope == "global":
            allowed_access_levels.insert(0, "global")
        return {
            "success": True,
            "data": data,
            "allowed_access_levels": allowed_access_levels,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MCP servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.post("")
async def create_mcp_server_route(
    request: CreateMcpServerRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的 MCP 服务器"""
    await require_permission(db, current_user, "mcp.create")
    # 校验传输类型
    valid_transports = ("sse", "streamable_http", "stdio")
    if request.transport not in valid_transports:
        raise HTTPException(status_code=400, detail=f"传输类型必须是 {', '.join(valid_transports)} 之一")

    # 根据传输类型校验必填字段
    if request.transport in ("sse", "streamable_http") and not request.url:
        raise HTTPException(status_code=400, detail=f"传输类型为 {request.transport} 时，url 必填")
    if request.transport == "stdio" and not request.command:
        raise HTTPException(status_code=400, detail="传输类型为 stdio 时，command 必填")

    requested_share_config = request.share_config or {
        "access_level": "user",
        "department_ids": [],
        "user_uids": [current_user.uid],
    }
    effective_share_config = await validate_share_config(
        db,
        current_user,
        "mcp.share",
        requested_share_config,
        owner_uid=current_user.uid,
        department_id=current_user.department_id,
    )
    try:
        server = await create_mcp_server(
            db,
            slug=request.slug,
            name=request.name,
            transport=request.transport,
            url=request.url,
            command=request.command,
            args=request.args,
            env=request.env,
            description=request.description,
            headers=request.headers,
            timeout=request.timeout,
            sse_read_timeout=request.sse_read_timeout,
            tags=request.tags,
            icon=request.icon,
            created_by=current_user.username,
        )
        server.created_by_uid = current_user.uid
        server.department_id = current_user.department_id
        server.share_config = effective_share_config
        await db.commit()
        await db.refresh(server)
        return {"success": True, "data": await _serialize_mcp(db, current_user, server)}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to create MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.get("/{slug}")
async def get_mcp_server_route(
    slug: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个 MCP 服务器配置"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.view")
        return {"success": True, "data": await _serialize_mcp(db, current_user, server)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{slug}")
async def update_mcp_server_route(
    slug: str,
    request: UpdateMcpServerRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """更新 MCP 服务器配置"""
    # 校验传输类型
    valid_transports = ("sse", "streamable_http", "stdio")
    if request.transport is not None and request.transport not in valid_transports:
        raise HTTPException(status_code=400, detail=f"传输类型必须是 {', '.join(valid_transports)} 之一")

    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.update")
        fields_set = request.model_fields_set
        update_kwargs = {}
        if "env" in fields_set:
            update_kwargs["env"] = request.env

        server = await update_mcp_server(
            db,
            slug=slug,
            name=request.name,
            description=request.description,
            transport=request.transport,
            url=request.url,
            command=request.command,
            args=request.args,
            headers=request.headers,
            timeout=request.timeout,
            sse_read_timeout=request.sse_read_timeout,
            tags=request.tags,
            icon=request.icon,
            updated_by=current_user.username,
            **update_kwargs,
        )
        if "share_config" in fields_set:
            server.share_config = await validate_share_config(
                db,
                current_user,
                "mcp.share",
                request.share_config,
                owner_uid=server.created_by_uid,
                department_id=server.department_id,
            )
            await db.commit()
            await db.refresh(server)
        return {"success": True, "data": await _serialize_mcp(db, current_user, server)}
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.delete("/{slug}")
async def delete_mcp_server_route(
    slug: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 MCP 服务器"""
    try:
        # 检查是否为系统内置服务器
        server = await get_mcp_server(db, slug)
        if server:
            await _require_mcp_permission(db, current_user, server, "mcp.delete")
        if server and server.created_by == "system":
            raise HTTPException(status_code=403, detail="系统内置的 MCP 服务器无法删除")

        deleted = await delete_mcp_server(db, slug)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"服务器 '{slug}' 不存在")
        return {"success": True, "message": f"服务器 '{slug}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# === MCP 服务器操作 ===
# =============================================================================


@mcp.post("/{slug}/test")
async def test_mcp_server(
    slug: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """测试 MCP 服务器连接"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.test")

        try:
            tools = await get_all_mcp_tools(slug)
            return {
                "success": True,
                "message": f"连接成功，共发现 {len(tools)} 个工具",
                "tool_count": len(tools),
            }
        except Exception as test_error:
            raise HTTPException(status_code=500, detail=f"连接失败: {str(test_error)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{slug}/status")
async def update_mcp_server_status_route(
    slug: str,
    request: UpdateMcpServerStatusRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """更新 MCP 服务器启用状态"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.enable")
        is_enabled, server = await set_server_enabled(db, slug, request.enabled, current_user.username)
        return {
            "success": True,
            "enabled": is_enabled,
            "data": await _serialize_mcp(db, current_user, server),
            "message": f"MCP '{slug}' 已{'添加' if is_enabled else '移除'}",
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to toggle MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# === MCP 工具管理 ===
# =============================================================================


@mcp.get("/{slug}/tools")
async def get_mcp_server_tools(
    slug: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 MCP 服务器的工具列表"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.view")
        disabled_tools = server.disabled_tools or []

        try:
            # 获取所有工具（不过滤 disabled_tools）
            tools = await get_all_mcp_tools(slug)
            tool_list = []

            for tool in tools:
                original_name = tool.name
                unique_id = tool.metadata.get("id") if tool.metadata else original_name

                tool_info = {
                    "name": original_name,
                    "id": unique_id,
                    "description": getattr(tool, "description", ""),
                    "enabled": original_name not in disabled_tools,
                }
                # 提取参数信息
                if hasattr(tool, "args_schema") and tool.args_schema:
                    schema = tool.args_schema.schema() if hasattr(tool.args_schema, "schema") else {}
                    tool_info["parameters"] = schema.get("properties", {})
                    tool_info["required"] = schema.get("required", [])
                else:
                    tool_info["parameters"] = {}
                    tool_info["required"] = []
                tool_list.append(tool_info)

            return {
                "success": True,
                "data": tool_list,
                "total": len(tool_list),
            }
        except Exception as tool_error:
            logger.error(f"Failed to get tools from MCP server '{slug}': {tool_error}")
            raise HTTPException(status_code=500, detail=f"获取工具失败: {str(tool_error)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MCP server tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.post("/{slug}/tools/refresh")
async def refresh_mcp_server_tools(
    slug: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """刷新 MCP 服务器的工具列表（清除缓存重新获取）"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.test")

        try:
            # 获取所有工具（不过滤 disabled_tools）
            tools = await get_all_mcp_tools(slug)

            # 获取统计信息
            stats = get_mcp_tools_stats(slug)
            enabled_count = stats.get("enabled", len(tools)) if stats else len(tools)
            disabled_count = stats.get("disabled", 0) if stats else 0

            message = "工具列表已刷新"
            if disabled_count > 0:
                message += f"，{enabled_count} 个已启用，{disabled_count} 个已禁用"
            else:
                message += f"，共发现 {enabled_count} 个工具"

            return {
                "success": True,
                "message": message,
                "tool_count": enabled_count,
                "enabled_count": enabled_count,
                "disabled_count": disabled_count,
            }
        except Exception as tool_error:
            raise HTTPException(status_code=500, detail=f"刷新失败: {str(tool_error)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh MCP server tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{slug}/tools/{tool_name}/toggle")
async def toggle_mcp_server_tool_route(
    slug: str,
    tool_name: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """切换单个工具的启用状态"""
    try:
        server = await get_server_or_404(db, slug)
        await _require_mcp_permission(db, current_user, server, "mcp.enable")
        enabled, _ = await toggle_tool_enabled(db, slug, tool_name, current_user.username)
        return {
            "success": True,
            "tool_name": tool_name,
            "enabled": enabled,
            "message": f"工具 '{tool_name}' 已{'启用' if enabled else '禁用'}",
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to toggle MCP server tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))
