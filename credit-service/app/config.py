from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_name: str = "credit-service"
    log_level: str = "info"
    database_url: str = "postgresql+asyncpg://foc:foc@credit-db:5432/credit_db"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    order_events_exchange: str = "foc.order.events"
    user_events_exchange: str = "foc.user.events"
    credit_events_exchange: str = "foc.credit.events"
    order_events_queue: str = "credit-service.order-events"
    user_events_queue: str = "credit-service.user-events"
    initial_credit_allocation: int = 100
    # How many times a transiently failing order event is redelivered before the
    # consumer publishes a definitive failure reply (request/reply events only).
    event_retry_limit: int = 5
    # Observability: emit one JSON log line per record (containers) instead of a
    # human-readable line (local dev). See docs/observability.md.
    log_json: bool = False
    # Availability SLO used by the summary endpoint's error-budget arithmetic.
    availability_slo: float = 0.99

    @property
    def consumer_queues(self) -> list[str]:
        """The queues this service consumes (used for consumer metrics)."""
        return [self.order_events_queue, self.user_events_queue]


settings = Settings()
