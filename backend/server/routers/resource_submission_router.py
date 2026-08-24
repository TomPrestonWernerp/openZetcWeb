"""openZetcX 本地资源投稿与部门审核 API。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from openzetc.services.rbac_service import get_user_permission_map, require_permission
from openzetc.services.resource_submission_service import (
    approve_submission,
    get_submission,
    list_my_submissions,
    list_review_submissions,
    reject_submission,
    submit_resource,
)
from openzetc.storage.postgres.models_business import User

resource_submissions = APIRouter(prefix="/resource-submissions", tags=["resource-submissions"])


class ReviewRequest(BaseModel):
    comment: str | None = None


def _raise_value_error(exc: ValueError) -> None:
    message = str(exc)
    status_code = 409 if "已有待审核" in message or "已通过审核" in message or "已处理" in message else 400
    raise HTTPException(status_code=status_code, detail=message) from exc


@resource_submissions.post("")
async def create_resource_submission(
    resource_type: str = Form(...),
    manifest: str = Form(...),
    package: UploadFile | None = File(None),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await require_permission(db, current_user, "resource_submission.submit", owner_uid=current_user.uid)
    try:
        parsed = json.loads(manifest)
        if not isinstance(parsed, dict):
            raise ValueError("manifest 必须为 JSON 对象")
        item = await submit_resource(
            db,
            submitter=current_user,
            resource_type=resource_type,
            manifest=parsed,
            package_filename=package.filename if package else None,
            package_data=await package.read() if package else None,
        )
        return {"success": True, "data": item.to_dict()}
    except (json.JSONDecodeError, ValueError) as exc:
        _raise_value_error(ValueError("manifest JSON 无效") if isinstance(exc, json.JSONDecodeError) else exc)


@resource_submissions.get("/mine")
async def get_my_resource_submissions(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await require_permission(db, current_user, "resource_submission.submit", owner_uid=current_user.uid)
    items = await list_my_submissions(db, current_user)
    return {"success": True, "data": [item.to_dict() for item in items]}


@resource_submissions.get("/review-queue")
async def get_resource_review_queue(
    status: str = Query("pending"),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    permission_map = await get_user_permission_map(db, current_user)
    scope = permission_map.get("resource_submission.review")
    if not scope:
        raise HTTPException(status_code=403, detail="缺少权限：resource_submission.review")
    if scope == "own":
        raise HTTPException(status_code=403, detail="资源审核权限至少需要部门范围")
    try:
        items = await list_review_submissions(
            db,
            department_id=None if scope == "global" else current_user.department_id,
            status=status,
        )
    except ValueError as exc:
        _raise_value_error(exc)
    return {"success": True, "data": [item.to_dict() for item in items]}


async def _get_reviewable_submission(db: AsyncSession, current_user: User, submission_id: str):
    item = await get_submission(db, submission_id)
    if item is None:
        raise HTTPException(status_code=404, detail="投稿不存在")
    await require_permission(
        db,
        current_user,
        "resource_submission.review",
        department_id=item.department_id,
    )
    return item


@resource_submissions.post("/{submission_id}/approve")
async def approve_resource_submission(
    submission_id: str,
    payload: ReviewRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_reviewable_submission(db, current_user, submission_id)
    try:
        approved = await approve_submission(db, item=item, reviewer=current_user, comment=payload.comment)
        return {"success": True, "data": approved.to_dict()}
    except ValueError as exc:
        _raise_value_error(exc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"公开发布失败：{exc}") from exc


@resource_submissions.post("/{submission_id}/reject")
async def reject_resource_submission(
    submission_id: str,
    payload: ReviewRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_reviewable_submission(db, current_user, submission_id)
    try:
        rejected = await reject_submission(db, item=item, reviewer=current_user, comment=payload.comment)
        return {"success": True, "data": rejected.to_dict()}
    except ValueError as exc:
        _raise_value_error(exc)
