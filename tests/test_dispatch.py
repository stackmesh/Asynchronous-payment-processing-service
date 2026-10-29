import asyncio
from uuid import uuid4

import pytest

from app.exceptions import PaymentNotFound
from app.messaging.handler import dispatch
from app.messaging.topology import DLQ_ROUTING_KEY


class _Broker:
    def __init__(self) -> None:
        self.published: list[tuple[object, dict]] = []

    async def publish(self, message: object, **kwargs: object) -> None:
        self.published.append((message, kwargs))


def _payload() -> dict[str, str]:
    return {
        "event_id": str(uuid4()),
        "event_type": "payment.created",
        "payment_id": str(uuid4()),
    }


def test_invalid_payload_goes_straight_to_dlq() -> None:
    broker = _Broker()

    asyncio.run(dispatch(broker, {"event_type": "other"}, {}))

    assert len(broker.published) == 1
    assert broker.published[0][1]["routing_key"] == DLQ_ROUTING_KEY


def test_first_failure_is_scheduled_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(payment_id: object) -> None:
        raise RuntimeError("webhook down")

    monkeypatch.setattr("app.messaging.handler.process_payment", fail)
    broker = _Broker()
    payload = _payload()

    asyncio.run(dispatch(broker, payload, {}))

    message, kwargs = broker.published[0]
    assert message == payload
    assert kwargs["routing_key"] == "payments.retry.1"
    assert kwargs["headers"]["x-retry-count"] == 1
    assert "webhook down" in kwargs["headers"]["x-last-error"]


def test_third_failure_and_missing_payment_go_to_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(payment_id: object) -> None:
        raise RuntimeError("still down")

    monkeypatch.setattr("app.messaging.handler.process_payment", fail)
    broker = _Broker()

    asyncio.run(dispatch(broker, _payload(), {"x-retry-count": 2}))

    assert broker.published[0][1]["routing_key"] == DLQ_ROUTING_KEY
    assert broker.published[0][1]["headers"]["x-retry-count"] == 3

    async def missing(payment_id: object) -> None:
        raise PaymentNotFound(payment_id)  # type: ignore[arg-type]

    monkeypatch.setattr("app.messaging.handler.process_payment", missing)
    broker = _Broker()
    asyncio.run(dispatch(broker, _payload(), {}))
    assert broker.published[0][1]["routing_key"] == DLQ_ROUTING_KEY
