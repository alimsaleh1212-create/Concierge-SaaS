import uuid
from typing import Any

import redis.asyncio as aioredis
from minio import Minio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.cms_content import CmsContent
from app.models.conversation import Conversation
from app.models.embedding import Embedding
from app.models.lead import Lead
from app.models.message import Message
from app.models.tenant import Tenant
from app.models.user import User
from app.models.widget import Widget

# In-memory set of tenants currently being erased — prevents concurrent erasure
_erasure_in_progress: set[uuid.UUID] = set()


async def erase_tenant(
    session: AsyncSession,
    actor_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """Full right-to-erasure per FR-008. Deletion order is strict and must not change."""
    from fastapi import HTTPException

    if tenant_id in _erasure_in_progress:
        raise HTTPException(status_code=409, detail="Erasure already in progress for this tenant")

    _erasure_in_progress.add(tenant_id)
    try:
        settings = get_settings()

        # 1. Redis — delete all session keys for this tenant
        redis_client = aioredis.from_url(settings.REDIS_URL)
        try:
            pattern = f"session:{tenant_id}:*"
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)
        finally:
            await redis_client.aclose()

        # 2. pgvector embeddings (hard delete — no is_deleted on embeddings)
        await session.execute(
            delete(Embedding).where(Embedding.tenant_id == tenant_id)
        )

        # 3. MinIO blobs — delete objects in both buckets prefixed by tenant_id
        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        for bucket in ("concierge-cms", "concierge-widget"):
            try:
                objects = minio_client.list_objects(bucket, prefix=f"{tenant_id}/", recursive=True)
                for obj in objects:
                    minio_client.remove_object(bucket, obj.object_name)
            except Exception:
                pass  # bucket may not exist or be empty — continue erasure

        # 4. Postgres rows — strict deletion order to satisfy FK constraints
        await session.execute(delete(Message).where(Message.tenant_id == tenant_id))
        await session.execute(delete(Lead).where(Lead.tenant_id == tenant_id))
        await session.execute(delete(Conversation).where(Conversation.tenant_id == tenant_id))
        await session.execute(delete(Embedding).where(Embedding.tenant_id == tenant_id))
        await session.execute(delete(CmsContent).where(CmsContent.tenant_id == tenant_id))
        await session.execute(delete(Widget).where(Widget.tenant_id == tenant_id))
        await session.execute(delete(User).where(User.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        # 5. audit_log entry written LAST — proves erasure completed
        session.add(AuditLog(
            actor_id=actor_id,
            actor_role="tenant_manager",
            tenant_id=None,  # tenant row no longer exists
            action="tenant.erased",
            metadata_={"erased_tenant_id": str(tenant_id)},
        ))
        await session.flush()

    finally:
        _erasure_in_progress.discard(tenant_id)
