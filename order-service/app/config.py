from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "order-service"
    log_level: str = "info"
    database_url: str = "postgresql+asyncpg://foc:foc@order-db:5432/order_db"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    order_events_exchange: str = "foc.order.events"


settings = Settings()
