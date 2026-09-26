from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "user-service"
    log_level: str = "info"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://foc:foc@user-db:5432/user_db"
    jwt_secret: str = ""
    jwt_access_token_ttl: int = 3600
    jwt_refresh_token_ttl: int = 86400
    initial_credit_allocation: int = 100
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    user_events_exchange: str = "foc.user.events"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "no-reply@foc.local"
    smtp_starttls: bool = True
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_display_name: str = "System Administrator"
    bootstrap_admin_contact_number: str | None = None


settings = Settings()
