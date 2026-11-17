from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables or .env."""

    app_name: str = "Office Task & Performance Management System"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "unsafe-development-key-change-before-deployment"
    session_max_age_seconds: int = 28_800
    office_timezone: str = "Africa/Dar_es_Salaam"
    database_url: str = "postgresql+psycopg://officetask:officetask@localhost:5432/officetask"
    upload_dir: str = "./storage/uploads"
    max_upload_size_mb: int = 20
    backup_dir: str = "./storage/backups"
    backup_retention_days: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def require_production_secret(self):
        if self.app_env.lower() == "production" and (
            len(self.secret_key) < 32
            or self.secret_key.startswith("unsafe-")
            or "replace" in self.secret_key.lower()
        ):
            raise ValueError("Production requires a unique, non-placeholder SECRET_KEY of at least 32 characters")
        if self.max_upload_size_mb <= 0:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be greater than zero")
        try:
            ZoneInfo(self.office_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("OFFICE_TIMEZONE must be a valid IANA timezone") from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
