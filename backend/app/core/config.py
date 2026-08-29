"""Configuracao central da aplicacao.

Unico ponto do codigo autorizado a ler variaveis de ambiente. Nenhum outro
modulo deve chamar os.getenv — ver planejamento/ordens.md, missao M2.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Identidade da empresa. Serve para configuracao e identificacao,
    # NUNCA como mecanismo de controle de acesso (planejamento/regras.md).
    company_name: str = "Empresa"
    company_slug: str = "empresa"

    app_env: AppEnv = "development"
    debug: bool = False
    log_level: str = "INFO"

    telegram_bot_token: str = ""
    telegram_use_webhook: bool = False
    telegram_webhook_secret: str = ""

    database_url: str = "postgresql+asyncpg://traffic:traffic@postgres:5432/traffic_bot"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = ""
    encryption_key: str = ""
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14

    conversion_webhook_secret: str = ""
    webhook_timestamp_tolerance_seconds: int = 300

    api_domain: str = "localhost"
    web_domain: str = "localhost"
    cors_origins: str = "http://localhost:5173"

    rate_limit_login_per_minute: int = 5
    rate_limit_webhook_per_minute: int = 120
    rate_limit_telegram_per_minute: int = 30

    consent_version: int = 1
    min_age: int = 18
    followup_delay_minutes: int = 60

    n8n_webhook_url: str = ""

    #: Volume onde ficam imagens/videos do funil. Montado no compose; nunca
    #: servido diretamente pela web — o bot le do disco e envia como arquivo.
    media_root: str = "/app/media"
    max_media_mb: int = 20

    @property
    def tenant_id(self) -> str:
        """Identificador do tenant deste deployment.

        Na arquitetura atual ha um deployment (e um banco) por empresa, entao
        o tenant e fixo. A coluna existe em todas as tabelas para permitir
        migracao futura a multi-tenant sem reescrever o schema.
        """
        return self.company_slug

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    def validate_runtime(self, service: str = "api") -> None:
        """Falha cedo se um segredo obrigatorio estiver ausente.

        Chamado no startup de cada servico. O token do Telegram so bloqueia o
        proprio bot (e producao) — assim a API e o dashboard sobem para teste
        antes de haver bot criado no BotFather. Em producao a exigencia e
        maior: nenhum segredo pode ficar vazio.
        """
        missing: list[str] = []
        if not self.jwt_secret:
            missing.append("JWT_SECRET")
        if not self.telegram_bot_token and (service == "bot" or self.is_production):
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.telegram_use_webhook and not self.telegram_webhook_secret:
            missing.append("TELEGRAM_WEBHOOK_SECRET")
        if self.is_production:
            if not self.encryption_key:
                missing.append("ENCRYPTION_KEY")
            if not self.conversion_webhook_secret:
                missing.append("CONVERSION_WEBHOOK_SECRET")
            if self.debug:
                raise RuntimeError("DEBUG=true nao e permitido com APP_ENV=production")
        if missing:
            raise RuntimeError(
                "Variaveis de ambiente obrigatorias ausentes: " + ", ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "Field"]
