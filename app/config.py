from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = Field(default="dev-api-key", min_length=8)

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50

    gateway_success_rate: float = 0.9
    gateway_min_delay_seconds: float = 2.0
    gateway_max_delay_seconds: float = 5.0

    webhook_max_attempts: int = 3
    webhook_timeout_seconds: float = 10.0
    webhook_backoff_seconds: float = 1.0

    processing_max_attempts: int = 3
    prefetch_count: int = 10

    @model_validator(mode="after")
    def check_ranges(self) -> "Settings":
        if not 0 <= self.gateway_success_rate <= 1:
            raise ValueError("GATEWAY_SUCCESS_RATE must be between 0 and 1")
        if self.gateway_min_delay_seconds < 0:
            raise ValueError("GATEWAY_MIN_DELAY_SECONDS must be >= 0")
        if self.gateway_min_delay_seconds > self.gateway_max_delay_seconds:
            raise ValueError("GATEWAY_MIN_DELAY_SECONDS must be <= GATEWAY_MAX_DELAY_SECONDS")
        if self.webhook_max_attempts < 1:
            raise ValueError("WEBHOOK_MAX_ATTEMPTS must be >= 1")
        if self.webhook_backoff_seconds < 0:
            raise ValueError("WEBHOOK_BACKOFF_SECONDS must be >= 0")
        if self.processing_max_attempts < 1:
            raise ValueError("PROCESSING_MAX_ATTEMPTS must be >= 1")
        if self.outbox_batch_size < 1:
            raise ValueError("OUTBOX_BATCH_SIZE must be >= 1")
        if self.prefetch_count < 1:
            raise ValueError("PREFETCH_COUNT must be >= 1")
        return self


settings = Settings()
