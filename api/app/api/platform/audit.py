import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.services.auth_service import require_role

router = APIRouter(prefix="/platform/audit-log", tags=["platform"])

_tenant_manager = require_role("tenant_manager")


@router.get("", status_code=200)
async def get_audit_log(
    tenant_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    if tenant_id is not None:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)

    result = await session.execute(stmt)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": str(e.id),
                "actor_id": str(e.actor_id),
                "actor_role": e.actor_role,
                "tenant_id": str(e.tenant_id) if e.tenant_id else None,
                "action": e.action,
                "metadata": e.metadata_,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]
    }
