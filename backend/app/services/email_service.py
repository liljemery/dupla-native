import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(
            self._settings.smtp_host
            and self._settings.email_from
        )

    async def send_password_reset(self, to_email: str, reset_url: str) -> None:
        if not self.is_configured:
            logger.warning(
                "SMTP not configured (SMTP_HOST / EMAIL_FROM); password reset email not sent to %s",
                to_email,
            )
            return

        subject = "Restablecer contraseña — Dupla"
        text_body = (
            "Recibimos una solicitud para restablecer tu contraseña en Dupla.\n\n"
            f"Abre este enlace para elegir una nueva contraseña (válido {self._settings.password_reset_token_expire_minutes} minutos):\n"
            f"{reset_url}\n\n"
            "Si no solicitaste este cambio, ignora este correo.\n"
        )
        html_body = (
            "<p>Recibimos una solicitud para restablecer tu contraseña en <strong>Dupla</strong>.</p>"
            f"<p><a href=\"{reset_url}\">Restablecer contraseña</a></p>"
            f"<p>El enlace expira en {self._settings.password_reset_token_expire_minutes} minutos.</p>"
            "<p>Si no solicitaste este cambio, ignora este correo.</p>"
        )

        message = EmailMessage()
        message["From"] = (
            f"{self._settings.email_from_name} <{self._settings.email_from}>"
            if self._settings.email_from_name
            else self._settings.email_from
        )
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_user or None,
            password=self._settings.smtp_password or None,
            start_tls=self._settings.smtp_use_tls,
            use_tls=self._settings.smtp_use_ssl,
        )
