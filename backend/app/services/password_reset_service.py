from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_token_repository import PasswordResetTokenRepository
from app.repositories.user_repository import UserRepository
from app.security.password import hash_password
from app.security.reset_token import generate_reset_token, hash_reset_token
from app.services.email_service import EmailService

settings = get_settings()

GENERIC_RESET_MESSAGE = (
    "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
)


class PasswordResetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = PasswordResetTokenRepository(session)
        self._email = EmailService()

    async def request_reset(self, email: str) -> str:
        user = await self._users.get_by_email(email.strip())
        if user is None:
            return GENERIC_RESET_MESSAGE

        await self._tokens.invalidate_unused_for_user(user.id)

        plain_token = generate_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.password_reset_token_expire_minutes
        )
        self._tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_reset_token(plain_token),
                expires_at=expires_at,
            )
        )
        await self._session.commit()

        reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={plain_token}"
        await self._email.send_password_reset(user.email, reset_url)

        return GENERIC_RESET_MESSAGE

    async def reset_password(self, token: str, new_password: str) -> None:
        token_hash = hash_reset_token(token.strip())
        reset_row = await self._tokens.get_valid_by_hash(token_hash)
        if reset_row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enlace inválido o expirado. Solicita uno nuevo.",
            )

        user = await self._users.get_by_uuid(reset_row.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enlace inválido o expirado. Solicita uno nuevo.",
            )

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        await self._tokens.mark_used(reset_row.id)
        await self._tokens.invalidate_unused_for_user(user.id)
        await self._session.commit()
