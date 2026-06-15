from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.module import ModuleResponse
from app.services.module_service import ModuleService

router = APIRouter(prefix="/api", tags=["modules"])


@router.get(
    "/modules",
    response_model=list[ModuleResponse],
    summary="List modules",
    description="List all application modules. Response may be served from Redis cache.",
)
async def list_modules(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ModuleResponse]:
    svc = ModuleService(session)
    return await svc.list_modules()
