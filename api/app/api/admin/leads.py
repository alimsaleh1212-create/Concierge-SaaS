import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.lead_repo import LeadRepository
from app.services.auth_service import require_role

router = APIRouter(prefix="/admin/leads", tags=["admin"])

_tenant_admin = require_role("tenant_admin")


def _tenant_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["tenant_id"])


class LeadStatusUpdate(BaseModel):
    status: str  # new | contacted | closed


@router.get("", status_code=200)
async def list_leads(
    status: Optional[str] = Query(None, pattern="^(new|contacted|closed)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    repo = LeadRepository(session)
    if status:
        leads = await repo.list_by_status(tid, status)
    else:
        leads = await repo.all(tid)
    paginated = leads[offset: offset + limit]
    return {
        "leads": [
            {
                "id": str(lead.id),
                "status": lead.status,
                "intent": lead.intent,
                "visitor_name": lead.visitor_name,
                "visitor_email": lead.visitor_email,
                "created_at": lead.created_at.isoformat(),
            }
            for lead in paginated
        ]
    }


@router.patch("/{lead_id}", status_code=200)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    repo = LeadRepository(session)
    lead = await repo.update_status(lead_id, body.status, tid)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    await session.commit()
    return {"id": str(lead.id), "status": lead.status}
