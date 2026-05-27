import hashlib
import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session import get_client as get_redis
from app.models.audit_log import AuditLog
from app.models.lead import Lead

_SESSION_MAX = 3        # max capture_lead calls per conversation
_IP_MAX = 5             # max capture_lead calls per visitor IP per hour
_IP_TTL = 3600          # 1 hour in seconds

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
        visitor_ip: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.conversation_id = conversation_id
        self.session = session
        self.visitor_ip = visitor_ip

    async def _check_rate_limits(self) -> str | None:
        """Return an error string if rate-limited, else None."""
        redis = get_redis()

        session_key = f"capture_lead:session:{self.conversation_id}"
        session_count = await redis.incr(session_key)
        if session_count == 1:
            await redis.expire(session_key, 1800)
        if session_count > _SESSION_MAX:
            return "Lead not captured — too many lead capture attempts in this session."

        if self.visitor_ip:
            ip_hash = hashlib.sha256(self.visitor_ip.encode()).hexdigest()
            ip_key = f"capture_lead:ip:{ip_hash}"
            ip_count = await redis.incr(ip_key)
            if ip_count == 1:
                await redis.expire(ip_key, _IP_TTL)
            if ip_count > _IP_MAX:
                return "Lead not captured — rate limit exceeded. Please try again later."

        return None

    async def __call__(
        self,
        visitor_name: str,
        visitor_email: str,
        intent: str,
        visitor_phone: str | None = None,
        **_: Any,
    ) -> str:
        rate_error = await self._check_rate_limits()
        if rate_error:
            return rate_error

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
