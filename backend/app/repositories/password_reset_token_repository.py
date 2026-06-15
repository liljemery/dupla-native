from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken


class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, token: PasswordResetToken) -> None:
        self._session.add(token)

    async def get_valid_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def invalidate_unused_for_user(self, user_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

    async def mark_used(self, token_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(used_at=now)
        )

    async def delete_expired(self) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.expires_at <= now)
        )
