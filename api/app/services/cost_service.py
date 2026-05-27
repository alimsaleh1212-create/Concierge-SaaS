import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message

# Rough token cost estimate — update with real pricing when known
_COST_PER_MESSAGE_USD = 0.002


@dataclass
class CostUsage:
    tenant_id: uuid.UUID
    message_count: int
    cost_7d_usd: float


async def get_cost_usage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    days: int = 7,
) -> CostUsage:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id,
            Message.created_at >= since,
        )
    )
    count = result.scalar_one() or 0
    return CostUsage(
        tenant_id=tenant_id,
        message_count=count,
        cost_7d_usd=round(count * _COST_PER_MESSAGE_USD, 4),
    )
