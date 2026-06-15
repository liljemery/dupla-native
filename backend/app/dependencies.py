from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.user_permissions import can_view_budget, has_elevated_access, is_gerencia
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User, UserRole
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.auth_service import AuthService

WORKSPACE_HEADER = "x-workspace-uuid"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token",
    scheme_name="JWT",
)

_PASSWORD_CHANGE_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/me"),
        ("POST", "/api/auth/change-password"),
    }
)


def _allows_password_change_pending(method: str, path: str) -> bool:
    return (method.upper(), path) in _PASSWORD_CHANGE_ALLOWED


async def get_auth_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(session)


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    auth = AuthService(session)
    user = await auth.get_user_for_token(token)
    if user.must_change_password and not _allows_password_change_pending(request.method, request.url.path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes cambiar tu contraseña antes de continuar",
        )
    return user


async def require_elevated_access(current: Annotated[User, Depends(get_current_user)]) -> User:
    if not has_elevated_access(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol Gerencia o Líder de equipo",
        )
    return current


async def require_gerencia(current: Annotated[User, Depends(get_current_user)]) -> User:
    if not is_gerencia(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol Gerencia",
        )
    return current


async def require_budget_access(current: Annotated[User, Depends(get_current_user)]) -> User:
    if not can_view_budget(current):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol Arquitectura no tiene acceso a presupuesto",
        )
    return current


async def require_task_creator(current: Annotated[User, Depends(get_current_user)]) -> User:
    if current.role not in (
        UserRole.GERENCIA,
        UserRole.CONTROL,
        UserRole.PRESUPUESTO,
        UserRole.ARQUITECTURA,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado",
        )
    return current


async def require_task_operator(current: Annotated[User, Depends(get_current_user)]) -> User:
    if current.role not in (
        UserRole.GERENCIA,
        UserRole.CONTROL,
        UserRole.PRESUPUESTO,
        UserRole.ARQUITECTURA,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado",
        )
    return current


async def get_workspace_context(
    request: Request,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceContext:
    repo = WorkspaceRepository(session)
    if is_gerencia(current):
        header = request.headers.get(WORKSPACE_HEADER)
        if header and header.strip():
            try:
                ws_uuid = UUID(header.strip())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-Workspace-Uuid inválido",
                )
            ws = await repo.get_by_uuid(ws_uuid)
            if ws is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Workspace no encontrado",
                )
        else:
            ws = await repo.get_default_or_first()
            if ws is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No hay workspaces configurados",
                )
        return WorkspaceContext(workspace_id=ws.id, workspace=ws)

    ws_id = current.active_workspace_id
    if ws_id is None:
        memberships = await repo.list_workspaces_for_user(current.id)
        if memberships:
            ws_id = memberships[0].id
            current.active_workspace_id = ws_id
            await session.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes un workspace asignado",
            )
    if not await repo.user_is_member(current.id, ws_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso al workspace activo",
        )
    ws = await repo.get_by_id(ws_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace no encontrado",
        )
    return WorkspaceContext(workspace_id=ws.id, workspace=ws)
