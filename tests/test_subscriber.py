import asyncio
from uuid import uuid4

from faststream.rabbit import TestRabbitBroker

from app.messaging.broker import broker
from app.messaging.consumer_app import on_payment_new  # noqa: F401  (registers the subscriber)
from app.messaging.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW_ROUTING_KEY


def test_subscriber_decodes_payment_created(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_topology(_broker: object) -> None:
        return None

    async def fake_process(payment_id: object) -> None:
        seen["payment_id"] = payment_id

    monkeypatch.setattr("app.messaging.handler.ensure_topology", fake_topology)
    monkeypatch.setattr("app.messaging.handler.process_payment", fake_process)

    payment_id = uuid4()

    async def publish() -> None:
        async with TestRabbitBroker(broker) as test_broker:
            await test_broker.publish(
                {
                    "event_id": str(uuid4()),
                    "event_type": "payment.created",
                    "payment_id": str(payment_id),
                },
                exchange=PAYMENTS_EXCHANGE,
                routing_key=PAYMENTS_NEW_ROUTING_KEY,
            )

    asyncio.run(publish())
    assert seen["payment_id"] == payment_id
