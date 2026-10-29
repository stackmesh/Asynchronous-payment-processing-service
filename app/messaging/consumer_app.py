import asyncio
import logging
from contextlib import suppress

from faststream import FastStream
from faststream.rabbit import RabbitMessage

from app.db import engine
from app.messaging.broker import broker
from app.messaging.handler import handle_delivery
from app.messaging.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW_QUEUE, ensure_topology
from app.services.outbox import run_outbox_relay

logger = logging.getLogger(__name__)

app = FastStream(broker)

_stop = asyncio.Event()
_relay: asyncio.Task[None] | None = None


@broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE)
async def on_payment_new(message: RabbitMessage) -> None:
    """Single consumer: settle the payment and deliver the webhook."""
    await handle_delivery(broker, message)


@app.on_startup
async def connect_and_declare() -> None:
    # Topology must exist before the subscriber starts, otherwise a reject
    # could dead-letter into an exchange that has not been declared yet.
    await broker.connect()
    await ensure_topology(broker)


@app.after_startup
async def start_relay() -> None:
    global _relay
    _stop.clear()
    _relay = asyncio.create_task(run_outbox_relay(broker, _stop), name="outbox-relay")
    logger.info("outbox relay started")


@app.on_shutdown
async def stop_relay() -> None:
    _stop.set()
    if _relay is None:
        return
    _relay.cancel()
    with suppress(asyncio.CancelledError):
        await _relay
    logger.info("outbox relay stopped")


@app.after_shutdown
async def dispose_engine() -> None:
    await engine.dispose()
