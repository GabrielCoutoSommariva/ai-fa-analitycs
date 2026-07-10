from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LOCAL_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    app_name: str = "Farmacias Associadas BI"
    database_url: str = "postgresql://postgres@localhost:5432/db_farmacias_bi"
    database_pool_min_size: int = 1
    database_pool_max_size: int = 20
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_timeout_seconds: int = 25
    ai_max_concurrent_requests: int = 12
    ai_queue_timeout_seconds: int = 2
    external_auth_jwt_secret: str | None = None
    external_auth_login_url: str | None = None
    session_cookie_name: str = "farmacia_bi_session"
    session_max_age_seconds: int = 28800
    session_cookie_secure: bool = True
    support_email_provider: str = "smtp"
    support_report_to: str | None = None
    support_report_from: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 12
    emailjs_service_id: str | None = None
    emailjs_template_id: str | None = None
    emailjs_public_key: str | None = None
    emailjs_private_key: str | None = None
    emailjs_timeout_seconds: int = 12

    model_config = SettingsConfigDict(
        env_file=(ROOT_ENV_FILE, LOCAL_ENV_FILE),
        env_file_encoding="utf-8",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def external_auth_enabled(self) -> bool:
        return bool(self.external_auth_jwt_secret)

    @property
    def support_report_recipients(self) -> list[str]:
        if not self.support_report_to:
            return []
        return [email.strip() for email in self.support_report_to.split(",") if email.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
