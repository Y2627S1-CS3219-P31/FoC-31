# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "order-service"
    log_level: str = "info"
    database_url: str = "postgresql+asyncpg://foc:foc@order-db:5432/order_db"
    supplier_service_url: str = "http://supplier-service:8000"
    credit_service_url: str = "http://credit-service:8000"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    order_events_exchange: str = "foc.order.events"


settings = Settings()
