from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PaymentSnapshot:
    """Payment fields the webhook needs, detached from the database session."""

    payment_id: UUID
    amount: Decimal
    currency: str
    description: str | None
    metadata: dict[str, Any]
    status: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
    failure_reason: str | None
