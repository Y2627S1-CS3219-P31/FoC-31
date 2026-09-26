from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "api-gateway"
    log_level: str = "info"
    jwt_secret: str = "change-me-in-dev-only"
    user_service_url: str = "http://user-service:8000"
    supplier_service_url: str = "http://supplier-service:8000"
    order_service_url: str = "http://order-service:8000"
    credit_service_url: str = "http://credit-service:8000"
    notification_service_url: str = "http://notification-service:8000"
    cors_allowed_origins: str = "http://localhost:5173"


settings = Settings()
