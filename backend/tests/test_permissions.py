import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserModule, UserRole
from app.repositories.permission_repository import PermissionRepository
from app.services.permission_service import PermissionService
from app.security.password import hash_password


@pytest.mark.asyncio
async def test_permission_union_from_multiple_roles(session: AsyncSession):
    perm_repo = PermissionRepository(session)
    await perm_repo.ensure_catalog()
    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            email="multi@dupla.demo",
            first_name="Multi",
            last_name="Role",
            password_hash=hash_password("pass12345"),
        )
    )
    session.add(UserModule(user_id=user_id, module_id=1))
    await session.flush()
    await perm_repo.assign_roles_by_slugs(user_id, [UserRole.CONTROL.value, "TEAM_LEADER"])
    svc = PermissionService(session)
    user = await session.get(User, user_id)
    assert user is not None
    perms = await svc.resolve(user)
    assert "budget.view" in perms
    assert "admin.access" in perms
    assert "admin.users.create" not in perms


@pytest.mark.asyncio
async def test_permission_override_grant_and_deny(session: AsyncSession):
    perm_repo = PermissionRepository(session)
    await perm_repo.ensure_catalog()
    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            email="override@dupla.demo",
            first_name="Over",
            last_name="Ride",
            password_hash=hash_password("pass12345"),
        )
    )
    await session.flush()
    await perm_repo.assign_roles_by_slugs(user_id, [UserRole.ARQUITECTURA.value])
    await perm_repo.set_user_overrides(user_id, [("budget.view", True)])
    svc = PermissionService(session)
    user = await session.get(User, user_id)
    assert user is not None
    assert await svc.has(user, "budget.view")
    await perm_repo.set_user_overrides(user_id, [("budget.view", False)])
    svc2 = PermissionService(session)
    assert not await svc2.has(user, "budget.view")


@pytest.mark.asyncio
async def test_custom_role_starts_empty(session: AsyncSession):
    perm_repo = PermissionRepository(session)
    await perm_repo.ensure_catalog()
    role = await perm_repo.create_custom_role("CUSTOM_AUDITOR", "Auditor custom")
    keys = await perm_repo.list_role_permission_keys(role.id)
    assert keys == frozenset()
