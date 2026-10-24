"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Finance Automation"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = Field(..., description="Async PostgreSQL connection URL")
    DATABASE_URL_SYNC: str = Field(..., description="Sync PostgreSQL connection URL for Alembic")

    # Security
    SECRET_KEY: str = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # File Upload
    UPLOAD_DIR: Path = Path("./uploads")
    MAX_UPLOAD_SIZE_MB: int = 50

    # SMTP
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "notifications@example.com"
    SMTP_PASSWORD: str = "changeme"
    SMTP_FROM: str = "Finance Automation <notifications@example.com>"

    # Anonymization
    ANONYMIZATION_SALT: str = Field(..., min_length=16)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def database_url_sync_for_alembic(self) -> str:
        """Return sync URL with psycopg2 driver for Alembic."""
        return self.DATABASE_URL_SYNC


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()