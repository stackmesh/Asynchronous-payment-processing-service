import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.enums import Currency, PaymentStatus
from app.money import MONEY_QUANTUM


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("9999999999999999.99"), examples=["1500.50"])
    currency: Currency
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    @field_validator("amount")
    @classmethod
    def at_most_two_decimal_places(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(MONEY_QUANTUM)
        if value != quantized:
            raise ValueError("amount must have at most 2 decimal places")
        return quantized

    @field_validator("webhook_url")
    @classmethod
    def webhook_url_length(cls, value: HttpUrl) -> HttpUrl:
        if len(str(value)) > 2000:
            raise ValueError("webhook_url must be at most 2000 characters")
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_is_a_small_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("metadata must be at most 16KB")
        return value


class PaymentAccepted(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime


class PaymentDetail(BaseModel):
    payment_id: UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    failure_reason: str | None
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "payment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "amount": "1500.50",
                    "currency": "RUB",
                    "description": "Order 1001",
                    "metadata": {"order_id": "1001"},
                    "status": "pending",
                    "idempotency_key": "order-1001",
                    "webhook_url": "https://merchant.example/hooks/payments",
                    "failure_reason": None,
                    "created_at": "2026-10-29T12:00:00+00:00",
                    "processed_at": None,
                }
            ]
        }
    )
