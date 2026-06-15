from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.module import Module


class ModuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Module]:
        result = await self._session.execute(select(Module).order_by(Module.id))
        return list(result.scalars().all())

    async def get_by_id(self, module_id: int) -> Optional[Module]:
        result = await self._session.execute(select(Module).where(Module.id == module_id))
        return result.scalar_one_or_none()
