import logging
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from faststream.rabbit import RabbitBroker, RabbitMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import settings
from app.exceptions import PermanentProcessingError
from app.messaging.retry import (
    current_attempt,
    failure_destination,
    retry_headers,
    retry_queue_name,
    retry_ttl_ms,
    sanitize_header,
)
from app.messaging.topology import DLQ_ROUTING_KEY, DLX_EXCHANGE, ensure_topology
from app.models import PAYMENT_CREATED
from app.services.processing import process_payment

logger = logging.getLogger(__name__)


class PaymentCreatedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    event_type: Literal["payment.created"]
    payment_id: UUID


if PAYMENT_CREATED != "payment.created":
    raise RuntimeError("PAYMENT_CREATED drifted from the message contract")


async def handle_delivery(broker: RabbitBroker, message: RabbitMessage) -> None:
    await ensure_topology(broker)
    payload = await message.decode()
    await dispatch(broker, payload, dict(message.headers or {}))


async def dispatch(
    broker: RabbitBroker,
    payload: Any,
    headers: Mapping[str, Any],
) -> None:
    attempt = current_attempt(headers)

    if not isinstance(payload, dict):
        await publish_to_dlq(broker, {"unparsed": repr(payload)[:500]}, attempt, "payload is not an object")
        return

    try:
        event = PaymentCreatedEvent.model_validate(payload)
    except ValidationError as exc:
        await publish_to_dlq(broker, payload, attempt, f"invalid payload: {exc}")
        return

    if attempt > settings.processing_max_attempts:
        await publish_to_dlq(broker, payload, attempt, "retry count exceeded")
        return

    try:
        await process_payment(event.payment_id)
    except PermanentProcessingError as exc:
        logger.error("permanent failure payment_id=%s error=%s", event.payment_id, exc)
        await publish_to_dlq(broker, payload, attempt, str(exc))
    except Exception as exc:
        logger.exception(
            "processing failed payment_id=%s attempt=%s/%s",
            event.payment_id,
            attempt,
            settings.processing_max_attempts,
        )
        await route_failure(broker, payload, attempt, exc)


async def route_failure(
    broker: RabbitBroker,
    payload: dict[str, Any],
    attempt: int,
    error: BaseException,
) -> None:
    if failure_destination(attempt, settings.processing_max_attempts) == "dlq":
        await publish_to_dlq(broker, payload, attempt, str(error))
        return

    queue = retry_queue_name(attempt)
    logger.warning(
        "scheduling retry payment_id=%s attempt=%s delay_ms=%s queue=%s",
        payload.get("payment_id"),
        attempt,
        retry_ttl_ms(attempt),
        queue,
    )
    await broker.publish(
        payload,
        routing_key=queue,
        persist=True,
        mandatory=True,
        headers=retry_headers(attempt, error),
    )


async def publish_to_dlq(
    broker: RabbitBroker,
    payload: dict[str, Any],
    attempt: int,
    reason: str,
) -> None:
    logger.error(
        "sending to dlq payment_id=%s attempt=%s reason=%s",
        payload.get("payment_id"),
        attempt,
        sanitize_header(reason),
    )
    await broker.publish(
        payload,
        exchange=DLX_EXCHANGE,
        routing_key=DLQ_ROUTING_KEY,
        persist=True,
        mandatory=True,
        headers={
            "x-retry-count": attempt,
            "x-last-error": sanitize_header(reason),
            "x-original-queue": "payments.new",
        },
    )
