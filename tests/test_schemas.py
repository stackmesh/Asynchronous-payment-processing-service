from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.enums import Currency
from app.schemas import PaymentCreate


def _payload(**overrides) -> dict:
    data = {
        "amount": "10.50",
        "currency": "RUB",
        "description": "order",
        "metadata": {"order_id": "1"},
        "webhook_url": "https://merchant.example/hook",
    }
    data.update(overrides)
    return data


def test_accepts_string_amount_and_quantizes() -> None:
    payment = PaymentCreate.model_validate(_payload(amount="10.5"))
    assert payment.amount == Decimal("10.50")
    assert payment.currency is Currency.RUB


def test_rejects_extra_fraction_and_unknown_currency() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(amount="10.501"))
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(currency="GBP"))
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(amount="0"))


def test_metadata_must_be_an_object() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(metadata=["nope"]))
