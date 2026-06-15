from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import cache_get_json, cache_set_json
from app.config import get_settings
from app.repositories.module_repository import ModuleRepository
from app.schemas.module import ModuleResponse

settings = get_settings()

MODULES_CACHE_KEY = "api:modules:list:v1"


class ModuleService:
    def __init__(self, session: AsyncSession) -> None:
        self._modules = ModuleRepository(session)

    async def list_modules(self) -> list[ModuleResponse]:
        cached = await cache_get_json(MODULES_CACHE_KEY)
        if isinstance(cached, list):
            return [ModuleResponse.model_validate(x) for x in cached]
        rows = await self._modules.list_all()
        out = [ModuleResponse.model_validate(m) for m in rows]
        payload = [m.model_dump(mode="json") for m in out]
        await cache_set_json(MODULES_CACHE_KEY, payload, settings.cache_ttl_seconds)
        return out
