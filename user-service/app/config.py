from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "user-service"
    log_level: str = "info"
    database_url: str = "postgresql+asyncpg://foc:foc@user-db:5432/user_db"
    jwt_secret: str = "change-me-in-dev-only"
    jwt_access_token_ttl: int = 3600
    jwt_refresh_token_ttl: int = 86400
    initial_credit_allocation: int = 100
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"


settings = Settings()
