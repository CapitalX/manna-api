# SPDX-License-Identifier: AGPL-3.0-or-later
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Manna API"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    # Database – set DATABASE_URL directly (Railway provides this), or set
    # individual POSTGRES_* vars for local dev / Docker Compose.
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "manna"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "manna"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Railway gives postgresql://, asyncpg needs postgresql+asyncpg://
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Ensure it's the sync driver format
            if "+asyncpg" in url:
                url = url.replace("+asyncpg", "")
            return url
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # CORS – comma-separated list of allowed origins
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:8081,exp://localhost:8081"

    # Auth – must be set via .env or environment variables
    JWT_SECRET: str  # required — no default; must be set in .env
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
