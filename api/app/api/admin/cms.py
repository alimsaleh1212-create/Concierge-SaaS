import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_tenant_context
from app.repositories.cms_repo import CmsRepository
from app.services import cms_service
from app.services.auth_service import require_role

router = APIRouter(prefix="/admin/cms", tags=["admin"])

_tenant_admin = require_role("tenant_admin")


def _tenant_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["tenant_id"])


class CmsCreateRequest(BaseModel):
    title: str
    body: str
    content_type: str
    metadata: dict = {}


class CmsUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    content_type: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("", status_code=200)
async def list_cms(
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    repo = CmsRepository(session)
    items = await repo.list_active(tid)
    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "content_type": c.content_type,
                "created_at": c.created_at.isoformat(),
            }
            for c in items
        ]
    }


@router.post("", status_code=201)
async def create_cms(
    body: CmsCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    content = await cms_service.create_content(
        session,
        tid,
        {"title": body.title, "body": body.body, "content_type": body.content_type, "metadata_": body.metadata},
        background_tasks,
    )
    await session.commit()
    return {"id": str(content.id), "title": content.title, "content_type": content.content_type}


@router.patch("/{content_id}", status_code=200)
async def update_cms(
    content_id: uuid.UUID,
    body: CmsUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    content = await cms_service.update_content(session, content_id, tid, data, background_tasks)
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    await session.commit()
    return {"id": str(content.id), "title": content.title}


@router.delete("/{content_id}", status_code=200)
async def delete_cms(
    content_id: uuid.UUID,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    deleted = await cms_service.soft_delete_content(session, content_id, tid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Content not found")
    await session.commit()
    return {"status": "deleted", "id": str(content_id)}
