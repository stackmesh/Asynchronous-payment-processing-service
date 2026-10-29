import asyncio
import logging

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings
from app.messaging.retry import retry_queue_name, retry_ttl_ms

logger = logging.getLogger(__name__)

PAYMENTS_EXCHANGE_NAME = "payments"
PAYMENTS_NEW_QUEUE_NAME = "payments.new"
PAYMENTS_NEW_ROUTING_KEY = "payments.new"
DLX_EXCHANGE_NAME = "payments.dlx"
DLQ_QUEUE_NAME = "payments.dlq"
DLQ_ROUTING_KEY = "payments.dlq"

# Topic exchange so `payment.created` can later grow siblings without a new queue topology.
PAYMENTS_EXCHANGE = RabbitExchange(
    PAYMENTS_EXCHANGE_NAME,
    type=ExchangeType.TOPIC,
    durable=True,
)
DLX_EXCHANGE = RabbitExchange(
    DLX_EXCHANGE_NAME,
    type=ExchangeType.DIRECT,
    durable=True,
)

# Rejected messages (unexpected handler crashes) land in the DLQ via this queue's DLX.
# The handler itself prefers an explicit republish, so it can attach the error and the attempt.
PAYMENTS_NEW_QUEUE = RabbitQueue(
    PAYMENTS_NEW_QUEUE_NAME,
    durable=True,
    routing_key=PAYMENTS_NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)
DLQ_QUEUE = RabbitQueue(
    DLQ_QUEUE_NAME,
    durable=True,
    routing_key=DLQ_ROUTING_KEY,
)

_ready = False
_lock = asyncio.Lock()


def build_retry_queue(failed_attempt: int) -> RabbitQueue:
    """Classic queue with a per-queue TTL. On expiry RabbitMQ routes the message back.

    Quorum queues are a poor fit here: the delay is a queue-level message TTL, which
    is the classic-queue dead-letter pattern.
    """
    return RabbitQueue(
        retry_queue_name(failed_attempt),
        durable=True,
        arguments={
            "x-message-ttl": retry_ttl_ms(failed_attempt),
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
            "x-dead-letter-routing-key": PAYMENTS_NEW_ROUTING_KEY,
        },
    )


async def ensure_topology(broker: RabbitBroker) -> None:
    """Declare exchanges, queues and bindings. Safe to call on every delivery."""
    global _ready
    if _ready:
        return

    async with _lock:
        if _ready:
            return

        payments = await broker.declare_exchange(PAYMENTS_EXCHANGE)
        dlx = await broker.declare_exchange(DLX_EXCHANGE)

        new_queue = await broker.declare_queue(PAYMENTS_NEW_QUEUE)
        await new_queue.bind(payments, routing_key=PAYMENTS_NEW_ROUTING_KEY)

        dlq = await broker.declare_queue(DLQ_QUEUE)
        await dlq.bind(dlx, routing_key=DLQ_ROUTING_KEY)

        retry_queues = max(settings.processing_max_attempts - 1, 0)
        for attempt in range(1, retry_queues + 1):
            # Published through the default exchange (routing key = queue name).
            # No extra binding: the default exchange already points at the queue.
            await broker.declare_queue(build_retry_queue(attempt))

        _ready = True
        logger.info(
            "rabbitmq topology ready exchange=%s queue=%s dlq=%s retry_levels=%s",
            PAYMENTS_EXCHANGE_NAME,
            PAYMENTS_NEW_QUEUE_NAME,
            DLQ_QUEUE_NAME,
            retry_queues,
        )
