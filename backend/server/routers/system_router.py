import asyncio
import os
from pathlib import Path
from urllib.parse import quote

import aiofiles
import httpx
import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from openzetc import config, get_version
from openzetc.storage.postgres.models_business import User
from openzetc.utils.logging_config import logger

from server.utils.auth_middleware import get_admin_user, get_required_user, get_superadmin_user

system = APIRouter(prefix="/system", tags=["system"])

DESKTOP_RELEASE_DOWNLOAD_URL = "https://github.com/TomPrestonWernerp/openZetcX/releases/latest/download"
DESKTOP_RELEASE_MANIFEST_URLS = (
    f"{DESKTOP_RELEASE_DOWNLOAD_URL}/latest.yml",
    f"{DESKTOP_RELEASE_DOWNLOAD_URL}/latest-mac.yml",
)
DESKTOP_RELEASE_ASSET_SUFFIXES = (
    "Windows-x64.exe",
    "macOS-arm64.dmg",
    "macOS-x64.dmg",
)

# =============================================================================
# === 健康检查分组 ===
# =============================================================================


@system.get("/health")
async def health_check():
    """系统健康检查接口（公开接口）"""
    return {"status": "ok", "message": "服务正常运行", "version": get_version()}


@system.get("/discovery")
async def discovery():
    """系统能力发现接口（公开接口）"""
    return {
        "name": "openZetc",
        "version": get_version(),
        "api_prefix": "/api",
        "capabilities": {
            "cli": {
                "min_cli_version": "0.1.0",
                "browser_login": True,
                "api_key_auth": True,
                "remote_config": True,
                "kb_upload": True,
            }
        },
        "endpoints": {
            "health": "/api/system/health",
            "auth_me": "/api/auth/me",
            "cli_auth_sessions": "/api/auth/cli/sessions",
            "cli_auth_authorize": "/auth/cli/authorize",
        },
    }


# =============================================================================
# === 配置管理分组 ===
# =============================================================================


@system.get("/config")
async def get_config(current_user: User = Depends(get_required_user)):
    """获取系统配置"""
    return config.dump_config()


@system.post("/config")
async def update_config_single(key=Body(...), value=Body(...), current_user: User = Depends(get_admin_user)) -> dict:
    """更新单个配置项"""
    if not isinstance(key, str) or key not in type(config).model_fields:
        raise HTTPException(status_code=400, detail=f"未知配置项: {key}")
    if not config.can_update(key):
        raise HTTPException(status_code=400, detail=f"配置项不可修改: {key}")
    try:
        config.set_value(key, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config.save()
    return config.dump_config()


@system.post("/config/update")
async def update_config_batch(items: dict = Body(...), current_user: User = Depends(get_admin_user)) -> dict:
    """批量更新配置项"""
    try:
        config.update(items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config.save()
    return config.dump_config()


@system.get("/infrastructure-config")
async def get_infrastructure_settings(current_user: User = Depends(get_superadmin_user)) -> dict:
    """获取已脱敏的对象存储、向量数据库和图数据库配置。"""
    from openzetc.services.infrastructure_config_service import get_infrastructure_config

    return await get_infrastructure_config()


@system.post("/infrastructure-config")
async def update_infrastructure_settings(
    section: str = Body(...),
    values: dict = Body(...),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """保存单类基础设施配置，密钥掩码表示保留原值。"""
    from openzetc.services.infrastructure_config_service import save_infrastructure_config

    try:
        return await save_infrastructure_config(section, values, updated_by_uid=current_user.uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@system.post("/infrastructure-config/sources")
async def save_infrastructure_source_settings(
    section: str = Body(...),
    config_name: str = Body(...),
    values: dict = Body(...),
    source_id: int | None = Body(default=None),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """新增或修改一个对象存储、向量数据库或图数据库来源。"""
    from openzetc.services.infrastructure_config_service import save_infrastructure_source

    try:
        return await save_infrastructure_source(
            section,
            config_name,
            values,
            source_id=source_id,
            updated_by_uid=current_user.uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@system.post("/infrastructure-config/activate")
async def activate_infrastructure_source_settings(
    section: str = Body(...),
    source_id: int = Body(...),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """将指定来源设为该类型当前唯一的激活配置。"""
    from openzetc.services.infrastructure_config_service import activate_infrastructure_source

    try:
        return await activate_infrastructure_source(section, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@system.post("/infrastructure-config/delete")
async def delete_infrastructure_source_settings(
    section: str = Body(...),
    source_id: int = Body(...),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """删除一个未激活的基础设施来源。"""
    from openzetc.services.infrastructure_config_service import delete_infrastructure_source

    try:
        return await delete_infrastructure_source(section, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@system.post("/infrastructure-config/test")
async def test_infrastructure_settings(
    section: str = Body(...),
    values: dict = Body(...),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """使用当前表单值测试基础设施连接，不保存配置。"""
    from openzetc.services.infrastructure_config_service import test_infrastructure_connection

    try:
        return await test_infrastructure_connection(section, values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning(f"Infrastructure connection test failed for {section}: {exc}")
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}") from exc


@system.post("/infrastructure-config/reveal")
async def reveal_infrastructure_setting(
    section: str = Body(...),
    field: str = Body(...),
    source: str | None = Body(default=None),
    source_id: int | None = Body(default=None),
    current_user: User = Depends(get_superadmin_user),
) -> dict:
    """仅供超级管理员按需读取单个基础设施密钥。"""
    from openzetc.services.infrastructure_config_service import reveal_infrastructure_secret

    try:
        return await reveal_infrastructure_secret(section, field, source=source, source_id=source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@system.get("/logs")
async def get_system_logs(levels: str | None = None, current_user: User = Depends(get_admin_user)):
    """获取系统日志

    Args:
        levels: 可选的日志级别过滤，多个级别用逗号分隔，如 "INFO,ERROR,DEBUG,WARNING"
    """
    try:
        from openzetc.utils.logging_config import LOG_FILE

        # 解析日志级别过滤条件
        level_filter = None
        if levels:
            level_filter = set(level.strip().upper() for level in levels.split(",") if level.strip())

        #  修复 GBK 编码报错：强制 utf-8 读取，忽略错误
        async with aiofiles.open(LOG_FILE, encoding="utf-8", errors="ignore") as f:
            # 读取最后1000行
            lines = []
            async for line in f:
                filtered_line = line.rstrip("\n\r")
                # 如果指定了日志级别过滤，则按级别过滤
                if level_filter:
                    # 日志格式: 2025-03-10 08:26:37,269 - INFO - module - message
                    # 提取日志级别
                    parts = filtered_line.split(" - ")
                    if len(parts) >= 2 and parts[1].strip() in level_filter:
                        lines.append(filtered_line + "\n")
                    # 继续读取以保持行数统计准确
                    if len(lines) > 1000:
                        lines.pop(0)
                else:
                    lines.append(filtered_line + "\n")
                    if len(lines) > 1000:
                        lines.pop(0)

        log = "".join(lines)
        return {"log": log, "message": "success", "log_file": LOG_FILE}
    except Exception as e:
        logger.error(f"获取系统日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取系统日志失败: {str(e)}")


# =============================================================================
# === 信息管理分组 ===
# =============================================================================


async def load_info_config():
    """加载信息配置文件"""
    try:
        # 配置文件路径
        brand_file_path = os.environ.get("OPENZETC_BRAND_FILE_PATH", "package/openzetc/config/static/info.local.yaml")
        config_path = Path(brand_file_path)

        # 检查文件是否存在
        if not config_path.exists():
            logger.debug(f"The config file {config_path} does not exist, using default config")
            config_path = Path("package/openzetc/config/static/info.template.yaml")

        # 异步读取配置文件
        async with aiofiles.open(config_path, encoding="utf-8") as file:
            content = await file.read()

        # 注入版本号占位符
        content = content.replace("{{OPENZETC_VERSION}}", get_version())

        config = yaml.safe_load(content)

        return config

    except Exception as e:
        logger.error(f"Failed to load info config: {e}")
        return {}


@system.get("/info")
async def get_info_config():
    """获取系统信息配置（公开接口，无需认证）"""
    try:
        config = await load_info_config()
        return {"success": True, "data": config}
    except Exception as e:
        logger.error(f"获取信息配置失败: {e}")
        raise HTTPException(status_code=500, detail="获取信息配置失败")


def _build_desktop_release(manifests: list[dict]) -> dict:
    versions = {str(manifest.get("version", "")).strip() for manifest in manifests}
    versions.discard("")
    if len(versions) != 1:
        raise ValueError("桌面端更新清单版本不一致")

    assets = []
    for manifest in manifests:
        for item in manifest.get("files", []):
            name = str(item.get("url", "")).strip()
            if name.endswith(DESKTOP_RELEASE_ASSET_SUFFIXES):
                assets.append(
                    {
                        "name": name,
                        "browser_download_url": f"{DESKTOP_RELEASE_DOWNLOAD_URL}/{quote(name)}",
                    }
                )

    if len(assets) != len(DESKTOP_RELEASE_ASSET_SUFFIXES):
        raise ValueError("桌面端更新清单缺少安装包")

    version = versions.pop()
    return {"tag_name": version if version.startswith("v") else f"v{version}", "assets": assets}


@system.get("/desktop-release")
async def get_desktop_release(response: Response):
    """获取最新桌面端版本及安装包（公开接口）"""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            manifest_responses = await asyncio.gather(
                *(client.get(url, headers={"Cache-Control": "no-cache"}) for url in DESKTOP_RELEASE_MANIFEST_URLS)
            )

        manifests = []
        for manifest_response in manifest_responses:
            manifest_response.raise_for_status()
            manifests.append(yaml.safe_load(manifest_response.content.decode("utf-8")))

        response.headers["Cache-Control"] = "no-store"
        return _build_desktop_release(manifests)
    except (httpx.HTTPError, UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
        logger.warning(f"获取最新桌面端发布信息失败: {exc}")
        raise HTTPException(status_code=502, detail="暂时无法获取最新桌面端版本") from exc


@system.post("/info/reload")
async def reload_info_config(current_user: User = Depends(get_admin_user)):
    """重新加载信息配置"""
    try:
        config = await load_info_config()
        return {"success": True, "message": "配置重新加载成功", "data": config}
    except Exception as e:
        logger.error(f"重新加载信息配置失败: {e}")
        raise HTTPException(status_code=500, detail="重新加载信息配置失败")


# =============================================================================
# === OCR服务分组 ===
# =============================================================================


@system.get("/ocr/health")
async def check_ocr_services_health(current_user: User = Depends(get_admin_user)):
    """
    检查所有OCR服务的健康状态
    返回各个OCR服务的可用性信息
    """
    from openzetc.knowledge.parser.factory import DocumentProcessorFactory

    try:
        # 使用统一的健康检查接口
        health_status = await DocumentProcessorFactory.check_all_health_async()

        # 格式化健康检查响应
        formatted_status = {}
        for service_name, health_info in health_status.items():
            formatted_status[service_name] = {
                "status": health_info.get("status", "unknown"),
                "message": health_info.get("message", ""),
                "details": health_info.get("details", {}),
            }

        # 计算整体健康状态
        overall_status = (
            "healthy" if any(svc["status"] == "healthy" for svc in formatted_status.values()) else "unhealthy"
        )

        return {
            "overall_status": overall_status,
            "services": formatted_status,
            "message": "OCR服务健康检查完成",
        }

    except Exception as e:
        logger.error(f"OCR健康检查失败: {str(e)}")
        return {
            "overall_status": "error",
            "services": {},
            "message": f"OCR健康检查失败: {str(e)}",
        }
