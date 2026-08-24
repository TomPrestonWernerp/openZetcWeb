"""本地资源投稿、部门审核与公共资源发布。"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openzetc.agents.skills.service import confirm_skill_install_draft, prepare_skill_upload
from openzetc.repositories.agent_repository import AgentRepository
from openzetc.storage.postgres.models_business import MCPServer, ResourceSubmission, User
from openzetc.utils.datetime_utils import utc_now_naive

RESOURCE_TYPES = {"agent", "skill", "mcp"}
SUBMISSION_STATUSES = {"pending", "reviewing", "approved", "rejected"}
MAX_SKILL_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_SKILL_ARCHIVE_ENTRIES = 1_000
GLOBAL_SHARE_CONFIG = {"access_level": "global", "department_ids": [], "user_uids": []}
SENSITIVE_KEY_RE = re.compile(r"(?:secret|password|passwd|token|api[_-]?key|authorization|cookie)", re.I)


def _clean_text(value: Any, *, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError("资源名称和标识不能为空")
    return text[:maximum]


def _clean_slug(value: Any) -> str:
    slug = _clean_text(value, maximum=128, required=True).lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug).strip("-_")
    if not slug:
        raise ValueError("资源标识无效")
    return slug


def _sanitize_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_mapping(item)
            for key, item in value.items()
            if not SENSITIVE_KEY_RE.search(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_mapping(item) for item in value]
    if isinstance(value, str):
        return value[:20_000]
    return value if isinstance(value, (int, float, bool)) or value is None else str(value)


def _sanitize_url(value: Any) -> str | None:
    raw = _clean_text(value, maximum=2_000)
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    query = urlencode([(key, val) for key, val in parse_qsl(parsed.query) if not SENSITIVE_KEY_RE.search(key)])
    return urlunsplit((parsed.scheme, host, parsed.path, query, ""))


def _sanitize_command_args(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    skip_next = False
    for raw_arg in value[:256]:
        if skip_next:
            skip_next = False
            continue
        arg = str(raw_arg)[:2_000]
        flag = arg.split("=", 1)[0].lstrip("-")
        if SENSITIVE_KEY_RE.search(flag):
            skip_next = "=" not in arg
            continue
        cleaned.append(arg)
    return cleaned


def sanitize_manifest(resource_type: str, manifest: dict[str, Any]) -> dict[str, Any]:
    cleaned = _sanitize_mapping(manifest)
    cleaned["slug"] = _clean_slug(cleaned.get("slug"))
    cleaned["name"] = _clean_text(cleaned.get("name"), maximum=128, required=True)
    cleaned["description"] = _clean_text(cleaned.get("description"), maximum=4_000)
    if resource_type == "mcp":
        transport = _clean_text(cleaned.get("transport"), maximum=32, required=True)
        if transport not in {"stdio", "sse", "streamable_http"}:
            raise ValueError("MCP transport 仅支持 stdio、sse 或 streamable_http")
        cleaned["transport"] = transport
        cleaned["url"] = _sanitize_url(cleaned.get("url"))
        cleaned["command"] = _clean_text(cleaned.get("command"), maximum=2_000) or None
        cleaned["args"] = _sanitize_command_args(cleaned.get("args"))
        # 投稿永不携带本地凭据；只保留需要由安装者重新配置的键名提示。
        cleaned["env_keys"] = sorted({str(key)[:128] for key in manifest.get("env_keys", []) if str(key).strip()})
        cleaned["header_keys"] = sorted(
            {str(key)[:128] for key in manifest.get("header_keys", []) if str(key).strip()}
        )
        cleaned.pop("env", None)
        cleaned.pop("headers", None)
    return cleaned


def validate_skill_package(filename: str | None, package_data: bytes | None) -> None:
    if not package_data:
        raise ValueError("Skill 投稿必须包含完整 ZIP 包")
    if len(package_data) > MAX_SKILL_PACKAGE_BYTES:
        raise ValueError("Skill ZIP 不能超过 10 MB")
    if not str(filename or "").lower().endswith(".zip"):
        raise ValueError("Skill 投稿包必须为 .zip")
    try:
        with zipfile.ZipFile(io.BytesIO(package_data), "r") as archive:
            names = archive.namelist()
            if len(names) > MAX_SKILL_ARCHIVE_ENTRIES:
                raise ValueError("Skill ZIP 文件数量过多")
            for name in names:
                normalized = name.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    raise ValueError("Skill ZIP 包含非法路径")
            if len([name for name in names if name.rstrip("/").endswith("SKILL.md")]) != 1:
                raise ValueError("Skill ZIP 必须且只能包含一个 SKILL.md")
    except zipfile.BadZipFile as exc:
        raise ValueError("Skill ZIP 无法读取") from exc


async def submit_resource(
    db: AsyncSession,
    *,
    submitter: User,
    resource_type: str,
    manifest: dict[str, Any],
    package_filename: str | None = None,
    package_data: bytes | None = None,
) -> ResourceSubmission:
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("resource_type 仅支持 agent、skill、mcp")
    if not submitter.department_id:
        raise ValueError("当前账号尚未加入部门，无法发起部门审核")
    cleaned = sanitize_manifest(resource_type, manifest)
    if resource_type == "skill":
        validate_skill_package(package_filename, package_data)
    else:
        package_filename = None
        package_data = None

    duplicate = await db.execute(
        select(ResourceSubmission.status).where(
            ResourceSubmission.resource_type == resource_type,
            ResourceSubmission.slug == cleaned["slug"],
            ResourceSubmission.submitted_by_uid == submitter.uid,
            ResourceSubmission.status.in_(["pending", "reviewing", "approved"]),
        )
    )
    duplicate_status = duplicate.scalar_one_or_none()
    if duplicate_status in {"pending", "reviewing"}:
        raise ValueError("该资源已有待审核投稿")
    if duplicate_status == "approved":
        raise ValueError("该资源已通过审核并公开")

    item = ResourceSubmission(
        submission_id=uuid4().hex,
        resource_type=resource_type,
        slug=cleaned["slug"],
        name=cleaned["name"],
        description=cleaned.get("description"),
        status="pending",
        manifest=cleaned,
        package_filename=package_filename,
        package_data=package_data,
        submitted_by_uid=submitter.uid,
        department_id=submitter.department_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_submission(db: AsyncSession, submission_id: str) -> ResourceSubmission | None:
    result = await db.execute(select(ResourceSubmission).where(ResourceSubmission.submission_id == submission_id))
    return result.scalar_one_or_none()


async def list_my_submissions(db: AsyncSession, submitter: User) -> list[ResourceSubmission]:
    result = await db.execute(
        select(ResourceSubmission)
        .where(ResourceSubmission.submitted_by_uid == submitter.uid)
        .order_by(ResourceSubmission.created_at.desc(), ResourceSubmission.id.desc())
    )
    return list(result.scalars().all())


async def list_review_submissions(
    db: AsyncSession,
    *,
    department_id: int | None,
    status: str = "pending",
) -> list[ResourceSubmission]:
    if status not in SUBMISSION_STATUSES:
        raise ValueError("投稿状态无效")
    stmt = select(ResourceSubmission).where(ResourceSubmission.status == status)
    if department_id is not None:
        stmt = stmt.where(ResourceSubmission.department_id == department_id)
    result = await db.execute(stmt.order_by(ResourceSubmission.created_at.asc(), ResourceSubmission.id.asc()))
    return list(result.scalars().all())


async def _load_submitter(db: AsyncSession, uid: str) -> User:
    result = await db.execute(select(User).where(User.uid == uid, User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("投稿用户已不存在")
    return user


async def _publish_agent(db: AsyncSession, item: ResourceSubmission, submitter: User):
    manifest = item.manifest or {}
    context = {
        "identity": manifest.get("identity") or manifest.get("prompt") or "",
        "source": "openzetcx_submission",
        "source_submission_id": item.submission_id,
        "recommended_skills": manifest.get("skills") or [],
        "recommended_mcp": manifest.get("mcp") or [],
    }
    agent = await AgentRepository(db).create(
        slug=item.slug,
        name=item.name,
        description=item.description,
        backend_id="ChatbotAgent",
        config_json={"context": context},
        share_config=GLOBAL_SHARE_CONFIG,
        created_by=submitter.uid,
        creator=submitter,
        share_validated=True,
    )
    agent.department_id = submitter.department_id
    await db.commit()
    await db.refresh(agent)
    return agent


async def _publish_skill(db: AsyncSession, item: ResourceSubmission, submitter: User):
    draft = await prepare_skill_upload(
        db,
        filename=item.package_filename or f"{item.slug}.zip",
        file_bytes=bytes(item.package_data or b""),
        operator=submitter,
    )
    results = await confirm_skill_install_draft(
        db,
        draft_id=draft["draft_id"],
        share_config=GLOBAL_SHARE_CONFIG,
        operator=submitter,
        created_by=submitter.uid,
        department_id=submitter.department_id,
        share_validated=True,
    )
    success = next((result for result in results if result.get("success")), None)
    if success is None:
        raise ValueError(results[0].get("error", "Skill 发布失败") if results else "Skill 发布失败")
    return success["skill"]


async def _publish_mcp(db: AsyncSession, item: ResourceSubmission, submitter: User):
    manifest = item.manifest or {}
    server = MCPServer(
        slug=item.slug,
        name=item.name,
        description=item.description,
        transport=manifest.get("transport"),
        url=manifest.get("url"),
        command=manifest.get("command"),
        args=manifest.get("args") or [],
        env={},
        headers={},
        timeout=manifest.get("timeout"),
        sse_read_timeout=manifest.get("sse_read_timeout"),
        tags=manifest.get("tags") or [],
        icon=manifest.get("icon"),
        enabled=1,
        disabled_tools=[],
        share_config=GLOBAL_SHARE_CONFIG,
        created_by=submitter.username,
        created_by_uid=submitter.uid,
        department_id=submitter.department_id,
        updated_by=submitter.username,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def approve_submission(
    db: AsyncSession,
    *,
    item: ResourceSubmission,
    reviewer: User,
    comment: str | None = None,
) -> ResourceSubmission:
    locked = await db.execute(
        select(ResourceSubmission).where(ResourceSubmission.id == item.id).with_for_update()
    )
    item = locked.scalar_one_or_none()
    if item is None:
        raise ValueError("投稿不存在")
    if item.status != "pending":
        raise ValueError("该投稿已处理或正在处理")
    item.status = "reviewing"
    item.reviewed_by_uid = reviewer.uid
    item.review_comment = _clean_text(comment, maximum=2_000)
    item.updated_at = utc_now_naive()
    await db.commit()
    try:
        submitter = await _load_submitter(db, item.submitted_by_uid)
        if item.resource_type == "agent":
            published = await _publish_agent(db, item, submitter)
            published_id, published_slug = published.id, published.slug
        elif item.resource_type == "skill":
            published = await _publish_skill(db, item, submitter)
            published_id, published_slug = published.get("id"), published.get("slug")
        else:
            published = await _publish_mcp(db, item, submitter)
            published_id, published_slug = published.id, published.slug
        item.status = "approved"
        item.published_resource_id = published_id
        item.published_slug = published_slug
        item.package_data = None
        item.reviewed_at = utc_now_naive()
        item.updated_at = utc_now_naive()
        await db.commit()
        await db.refresh(item)
        return item
    except Exception as exc:
        await db.rollback()
        current = await get_submission(db, item.submission_id)
        if current is not None:
            current.status = "pending"
            current.review_comment = f"发布失败：{exc}"[:2_000]
            current.updated_at = utc_now_naive()
            await db.commit()
        raise


async def reject_submission(
    db: AsyncSession,
    *,
    item: ResourceSubmission,
    reviewer: User,
    comment: str | None,
) -> ResourceSubmission:
    locked = await db.execute(
        select(ResourceSubmission).where(ResourceSubmission.id == item.id).with_for_update()
    )
    item = locked.scalar_one_or_none()
    if item is None:
        raise ValueError("投稿不存在")
    if item.status != "pending":
        raise ValueError("该投稿已处理或正在处理")
    reason = _clean_text(comment, maximum=2_000, required=True)
    item.status = "rejected"
    item.reviewed_by_uid = reviewer.uid
    item.review_comment = reason
    item.package_data = None
    item.reviewed_at = utc_now_naive()
    item.updated_at = utc_now_naive()
    await db.commit()
    await db.refresh(item)
    return item
