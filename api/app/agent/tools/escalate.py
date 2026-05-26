import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.conversation_repo import ConversationRepository

SCHEMA: dict[str, Any] = {
    "name": "escalate",
    "description": "Escalate the conversation to a human agent when you cannot resolve the visitor's request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Brief reason for escalation"},
        },
        "required": ["reason"],
    },
}


class EscalateTool:
    name = "escalate"
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

    async def __call__(self, reason: str, **_: Any) -> str:
        repo = ConversationRepository(self.session)
        await repo.set_escalated(self.conversation_id, self.tenant_id)

        self.session.add(AuditLog(
            actor_id=self.conversation_id,
            actor_role="member",
            tenant_id=self.tenant_id,
            action="conversation.escalated",
            metadata_={"reason": reason},
        ))
        await self.session.flush()
        return "Conversation escalated to a human agent."
