from functools import lru_cache
from typing import Annotated, Literal, Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_JWT_SECRET = "demo-secret-change-in-production-min-32-chars!!"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: Annotated[
        str,
        Field(
            default="postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla",
            description=(
                "Async SQLAlchemy URL. Default targets localhost (run Postgres on port 5432)."
            ),
        ),
    ] = "postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla"
    redis_url: Annotated[
        str,
        Field(
            default="redis://127.0.0.1:6379/0",
            description="Redis URL. Default targets localhost on port 6379.",
        ),
    ] = "redis://127.0.0.1:6379/0"
    processor_url: Annotated[
        str,
        Field(
            default="http://localhost:8001",
            description="Base URL of the dupla_chris processor microservice.",
        ),
    ] = "http://localhost:8001"
    coordination_url: Annotated[
        str,
        Field(
            default="http://localhost:8002",
            description="Base URL of the coordination / clash detection microservice.",
        ),
    ] = "http://localhost:8002"
    coordination_default_profile: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Fallback coordination profile slug when project has none (tortuga_c40, serena18, nasas09).",
        ),
    ] = None
    app_env: Annotated[
        Literal["development", "staging", "production"],
        Field(
            default="development",
            validation_alias=AliasChoices("APP_ENV"),
            description="Entorno de despliegue; en staging/production se validan secretos y smoke mode.",
        ),
    ] = "development"
    coordination_smoke_mode: Annotated[
        bool,
        Field(
            default=False,
            validation_alias=AliasChoices("COORDINATION_SMOKE_MODE"),
            description="Si true, coordination-service usa fixtures en lugar del motor Dupla.",
        ),
    ] = False
    dev_expose_reset_token: Annotated[
        bool,
        Field(
            default=False,
            validation_alias=AliasChoices("DEV_EXPOSE_RESET_TOKEN"),
            description="Solo development: incluir token de reset en la respuesta API (QA local sin SMTP).",
        ),
    ] = False
    jwt_secret: Annotated[str, Field(default=DEMO_JWT_SECRET)] = DEMO_JWT_SECRET
    jwt_algorithm: Annotated[str, Field(default="HS256")] = "HS256"
    access_token_expire_minutes: Annotated[int, Field(default=60, ge=1, le=60 * 24 * 7)] = 60
    cors_origins: Annotated[str, Field(default="http://localhost:5173,http://127.0.0.1:5173")] = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    cache_ttl_seconds: Annotated[int, Field(default=300, ge=1)] = 300
    architecture_module_id: Annotated[int, Field(default=1, ge=1)] = 1

    templates_dir: Annotated[str, Field(default="app/templates")] = "app/templates"
    upload_root: Annotated[
        str,
        Field(
            default="var/uploads",
            description="Directorio raíz para archivos de proyecto (DWG/DXF, etc.).",
        ),
    ] = "var/uploads"
    project_file_max_mb: Annotated[
        int,
        Field(
            default=200,
            ge=1,
            le=2048,
            description="Tamaño máximo por archivo de proyecto (MB). CAD/BIM suele superar 50 MB.",
        ),
    ] = 200
    openai_api_key: Annotated[
        Optional[str],
        Field(default=None, description="API key OpenAI: clasificación de archivos y Dupla Assistant (léela desde backend/.env)."),
    ] = None
    openai_model: Annotated[str, Field(default="gpt-4o-mini")] = "gpt-4o-mini"
    ai_assistant_context_ttl_seconds: Annotated[
        int,
        Field(
            default=604800,
            ge=60,
            le=60 * 60 * 24 * 90,
            description=(
                "TTL en Redis del historial del asistente IA por usuario (~7 días; cubre ~5 días laborales). "
                "Se renueva en cada mensaje (ventana deslizante)."
            ),
        ),
    ] = 604800
    ai_assistant_max_context_messages: Annotated[
        int,
        Field(
            default=40,
            ge=4,
            le=200,
            description="Máximo de mensajes user+assistant guardados en Redis (recorte por cola).",
        ),
    ] = 40

    aps_client_id: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("CLIENT_ID", "APS_CLIENT_ID"),
            description="Autodesk APS (Forge) client id para OSS + Model Derivative.",
        ),
    ] = None
    aps_client_secret: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("CLIENT_SECRET", "APS_CLIENT_SECRET"),
            description="Autodesk APS client secret.",
        ),
    ] = None
    aps_bucket_name: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("APS_BUCKET_NAME", "APS_BUCKET_KEY"),
            description="Clave del bucket OSS APS (única, minúsculas e hífen).",
        ),
    ] = None
    aps_region: Annotated[
        str,
        Field(
            default="US",
            validation_alias=AliasChoices("APS_REGION"),
            description="Región al crear bucket OSS (US, EMEA, …). Debe coincidir con la región de la app APS.",
        ),
    ] = "US"
    aps_bucket_policy: Annotated[
        str,
        Field(
            default="transient",
            validation_alias=AliasChoices("APS_BUCKET_POLICY"),
            description="Política OSS al crear bucket: transient (flujo traducción) o persistent.",
        ),
    ] = "transient"
    aps_translation_views: Annotated[
        str,
        Field(
            default="2d",
            validation_alias=AliasChoices("APS_TRANSLATION_VIEWS"),
            description="Vistas Model Derivative separadas por coma: 2d y/o 3d (p. ej. '2d' o '2d,3d').",
        ),
    ] = "2d"
    aps_failed_manifest_grace_polls: Annotated[
        int,
        Field(
            default=3,
            ge=0,
            le=20,
            validation_alias=AliasChoices("APS_FAILED_MANIFEST_GRACE_POLLS"),
            description="Reintentos de lectura de manifest tras failed (estado obsoleto en APS).",
        ),
    ] = 3
    aps_failed_manifest_grace_sleep_seconds: Annotated[
        int,
        Field(
            default=8,
            ge=1,
            le=120,
            validation_alias=AliasChoices("APS_FAILED_MANIFEST_GRACE_SLEEP_SECONDS"),
            description="Segundos entre lecturas de grace tras manifest failed.",
        ),
    ] = 8
    aps_auto_unique_object_name: Annotated[
        bool,
        Field(
            default=False,
            validation_alias=AliasChoices("APS_AUTO_UNIQUE_OBJECT_NAME"),
            description="Si true, añade timestamp al object key OSS para forzar URN nuevo por corrida.",
        ),
    ] = False
    aps_derivative_max_wait_seconds: Annotated[
        int,
        Field(default=600, ge=30, le=3600, description="Máximo de espera al job Model Derivative (background)."),
    ] = 600
    aps_derivative_poll_interval_seconds: Annotated[
        int,
        Field(default=5, ge=2, le=60, description="Intervalo entre consultas de estado del manifest."),
    ] = 5
    ga_fo_classification_confidence_min: Annotated[
        float,
        Field(default=0.55, ge=0.0, le=1.0, description="Umbral mínimo de confidence para auto-completar ítem GA-FO."),
    ] = 0.55
    ga_fo_aps_context_max_chars: Annotated[
        int,
        Field(default=32000, ge=4000, le=120000, description="Máximo de caracteres del resumen APS enviado a OpenAI."),
    ] = 32000

    frontend_url: Annotated[
        str,
        Field(
            default="http://localhost:5173",
            description="URL pública del frontend (enlaces en correos de restablecimiento de contraseña).",
        ),
    ] = "http://localhost:5173"
    password_reset_token_expire_minutes: Annotated[
        int,
        Field(default=60, ge=5, le=60 * 24, description="Validez del enlace de restablecimiento de contraseña."),
    ] = 60
    smtp_host: Annotated[
        Optional[str],
        Field(default=None, description="Host SMTP para envío de correos transaccionales."),
    ] = None
    smtp_port: Annotated[
        int,
        Field(default=587, ge=1, le=65535, description="Puerto SMTP (587 STARTTLS, 465 SSL)."),
    ] = 587
    smtp_user: Annotated[
        Optional[str],
        Field(default=None, description="Usuario SMTP (opcional si el relay no requiere auth)."),
    ] = None
    smtp_password: Annotated[
        Optional[str],
        Field(default=None, description="Contraseña SMTP."),
    ] = None
    smtp_use_tls: Annotated[
        bool,
        Field(default=True, description="Usar STARTTLS (típico en puerto 587)."),
    ] = True
    smtp_use_ssl: Annotated[
        bool,
        Field(default=False, description="Conexión SMTP directa por SSL (puerto 465)."),
    ] = False
    email_from: Annotated[
        Optional[str],
        Field(default=None, description="Remitente (From) de correos transaccionales."),
    ] = None
    email_from_name: Annotated[
        str,
        Field(default="Dupla", description="Nombre visible del remitente."),
    ] = "Dupla"

    @field_validator("database_url")
    @classmethod
    def database_must_be_postgres_async(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use postgresql+asyncpg:// scheme")
        return v

    @field_validator("redis_url")
    @classmethod
    def redis_must_be_redis(cls, v: str) -> str:
        if not v.startswith("redis://"):
            raise ValueError("redis_url must start with redis://")
        return v

    @field_validator("aps_bucket_policy")
    @classmethod
    def aps_bucket_policy_normalized(cls, v: str) -> str:
        s = (v or "transient").strip().lower()
        if s not in ("transient", "persistent"):
            raise ValueError("aps_bucket_policy must be 'transient' or 'persistent'")
        return s

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env != "development":
            if self.jwt_secret == DEMO_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET must be changed from the demo default when APP_ENV is staging or production. "
                    "Generate one with: openssl rand -hex 32"
                )
            if self.coordination_smoke_mode:
                raise ValueError(
                    "COORDINATION_SMOKE_MODE must be false when APP_ENV is staging or production."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
