import uuid
from typing import Any, Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: Type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def all(self, tenant_id: uuid.UUID) -> list[ModelT]:
        result = await self.session.execute(
            select(self.model).filter(
                self.model.tenant_id == tenant_id,
                self.model.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get(self, id: uuid.UUID, tenant_id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).filter(
                self.model.id == id,
                self.model.tenant_id == tenant_id,
                self.model.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> ModelT:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: uuid.UUID, data: dict[str, Any], tenant_id: uuid.UUID) -> ModelT | None:
        instance = await self.get(id, tenant_id)
        if instance is None:
            return None
        for key, value in data.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def soft_delete(self, id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        instance = await self.get(id, tenant_id)
        if instance is None:
            return False
        instance.is_deleted = True
        await self.session.flush()
        return True
