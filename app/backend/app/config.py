from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LOCAL_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    app_name: str = "Farmacias Associadas BI"
    database_url: str = "postgresql://postgres@localhost:5432/db_farmacias_bi"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    external_auth_jwt_secret: str | None = None
    external_auth_login_url: str | None = None
    session_cookie_name: str = "farmacia_bi_session"
    session_max_age_seconds: int = 28800
    session_cookie_secure: bool = True

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
