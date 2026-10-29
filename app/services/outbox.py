import asyncio
import logging
from datetime import datetime, timedelta, timezone

from faststream.rabbit import RabbitBroker
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionFactory
from app.enums import OutboxStatus
from app.messaging.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW_ROUTING_KEY
from app.models import OutboxEvent

logger = logging.getLogger(__name__)


async def run_outbox_relay(broker: RabbitBroker, stop: asyncio.Event) -> None:
    """Poll unpublished outbox rows and publish them.

    A full batch is followed immediately by another poll so a backlog drains
    without waiting for the interval. Publish happens before the row is marked
    published: a crash in between delivers the event twice, and the consumer
    treats a second delivery as a no-op once the payment is already settled.
    """
    while not stop.is_set():
        try:
            published = await publish_pending_batch(broker)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox relay iteration failed")
            published = 0

        if published:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.outbox_poll_interval_seconds)
        except TimeoutError:
            continue


async def publish_pending_batch(broker: RabbitBroker) -> int:
    published = 0
    async with SessionFactory() as session:
        async with session.begin():
            rows = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == OutboxStatus.PENDING.value,
                        OutboxEvent.next_attempt_at <= func.now(),
                    )
                    .order_by(OutboxEvent.created_at)
                    .limit(settings.outbox_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()

            for event in rows:
                try:
                    await broker.publish(
                        event.payload,
                        exchange=PAYMENTS_EXCHANGE,
                        routing_key=PAYMENTS_NEW_ROUTING_KEY,
                        persist=True,
                        mandatory=True,
                        message_id=str(event.id),
                        correlation_id=str(event.id),
                        headers={
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                        },
                    )
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = str(exc)[:2000]
                    delay = min(60, 2 ** event.attempts)
                    event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    logger.warning(
                        "outbox publish failed event_id=%s attempts=%s next_in=%ss error=%s",
                        event.id,
                        event.attempts,
                        delay,
                        exc,
                    )
                    continue

                event.status = OutboxStatus.PUBLISHED.value
                event.published_at = datetime.now(timezone.utc)
                event.last_error = None
                published += 1
                logger.info(
                    "outbox published event_id=%s payment_id=%s",
                    event.id,
                    event.aggregate_id,
                )

    return published
