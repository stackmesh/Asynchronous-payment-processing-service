import hashlib
import json
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.money import format_money

IDEMPOTENCY_CONSTRAINT = "uq_payments_idempotency_key"
UNIQUE_VIOLATION = "23505"


def canonical_request_hash(
    *,
    amount: Decimal,
    currency: str,
    description: str | None,
    metadata: dict[str, Any],
    webhook_url: str,
) -> str:
    """Stable hash of the create-payment body.

    Key order does not matter. Numerically equal amounts (10, 10.0, 10.00) match.
    """
    payload = {
        "amount": format_money(amount),
        "currency": currency,
        "description": description,
        "metadata": metadata,
        "webhook_url": webhook_url,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_idempotency_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    if getattr(orig, "sqlstate", None) != UNIQUE_VIOLATION:
        return False
    constraint = getattr(orig, "constraint_name", None)
    if constraint:
        return constraint == IDEMPOTENCY_CONSTRAINT
    return IDEMPOTENCY_CONSTRAINT in str(orig)
