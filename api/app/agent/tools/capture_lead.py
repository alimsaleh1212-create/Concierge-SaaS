import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.lead import Lead

SCHEMA: dict[str, Any] = {
    "name": "capture_lead",
    "description": "Capture a visitor's contact details as a sales lead.",
    "input_schema": {
        "type": "object",
        "properties": {
            "visitor_name": {"type": "string", "description": "Visitor's full name"},
            "visitor_email": {"type": "string", "description": "Visitor's email address"},
            "visitor_phone": {"type": "string", "description": "Visitor's phone number (optional)"},
            "intent": {"type": "string", "description": "What the visitor is interested in"},
        },
        "required": ["visitor_name", "visitor_email", "intent"],
    },
}


class _LeadInput(BaseModel):
    visitor_name: str
    visitor_email: str
    intent: str
    visitor_phone: str | None = None


class CaptureLeadTool:
    name = "capture_lead"
    schema = SCHEMA

    def __init__(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        self.tenant_id = tenant_id
        self.conversation_id = conversation_id
        self.session = session

    async def __call__(
        self,
        visitor_name: str,
        visitor_email: str,
        intent: str,
        visitor_phone: str | None = None,
        **_: Any,
    ) -> str:
        try:
            data = _LeadInput(
                visitor_name=visitor_name,
                visitor_email=visitor_email,
                intent=intent,
                visitor_phone=visitor_phone,
            )
        except ValidationError as exc:
            return f"Lead not captured — invalid input: {exc.error_count()} validation error(s)."

        lead = Lead(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id,
            visitor_name=data.visitor_name,
            visitor_email=data.visitor_email,
            visitor_phone=data.visitor_phone,
            intent=data.intent,
            status="new",
        )
        self.session.add(lead)
        await self.session.flush()

        self.session.add(AuditLog(
            actor_id=self.conversation_id,
            actor_role="member",
            tenant_id=self.tenant_id,
            action="lead.captured",
            metadata_={
                "lead_id": str(lead.id),
                "visitor_email": data.visitor_email,
            },
        ))
        await self.session.flush()
        return f"Lead captured successfully for {data.visitor_name}."
