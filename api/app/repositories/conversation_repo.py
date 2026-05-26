import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Conversation, session)

    async def get_by_session(self, session_id: str, tenant_id: uuid.UUID) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).filter(
                Conversation.session_id == session_id,
                Conversation.tenant_id == tenant_id,
                Conversation.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def set_escalated(self, id: uuid.UUID, tenant_id: uuid.UUID) -> Conversation | None:
        return await self.update(id, {"status": "escalated"}, tenant_id)

    async def set_closed(self, id: uuid.UUID, tenant_id: uuid.UUID) -> Conversation | None:
        return await self.update(id, {"status": "closed"}, tenant_id)
