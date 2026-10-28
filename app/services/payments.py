import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Currency, OutboxStatus, PaymentStatus
from app.exceptions import IdempotencyConflict
from app.idempotency import canonical_request_hash, is_idempotency_violation
from app.models import PAYMENT_CREATED, OutboxEvent, Payment
from app.money import format_money
from app.schemas import PaymentAccepted, PaymentCreate, PaymentDetail

logger = logging.getLogger(__name__)


async def create_payment(
    session: AsyncSession,
    body: PaymentCreate,
    idempotency_key: str,
) -> Payment:
    """Insert the payment and its outbox event in one transaction.

    The API does not talk to RabbitMQ. A successful commit means the relay will
    publish `payment.created`. A failed commit leaves neither row behind.
    """
    request_hash = canonical_request_hash(
        amount=body.amount,
        currency=body.currency.value,
        description=body.description,
        metadata=body.metadata,
        webhook_url=str(body.webhook_url),
    )
    now = datetime.now(timezone.utc)
    payment_id = uuid4()
    event_id = uuid4()

    payment = Payment(
        id=payment_id,
        amount=body.amount,
        currency=body.currency.value,
        description=body.description,
        metadata_=body.metadata,
        status=PaymentStatus.PENDING.value,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        webhook_url=str(body.webhook_url),
        created_at=now,
    )
    event = OutboxEvent(
        id=event_id,
        aggregate_type="payment",
        aggregate_id=payment_id,
        event_type=PAYMENT_CREATED,
        payload={
            "event_id": str(event_id),
            "event_type": PAYMENT_CREATED,
            "payment_id": str(payment_id),
            "amount": format_money(body.amount),
            "currency": body.currency.value,
            "created_at": now.isoformat(),
        },
        status=OutboxStatus.PENDING.value,
        attempts=0,
        created_at=now,
        next_attempt_at=now,
    )

    try:
        async with session.begin():
            session.add(payment)
            session.add(event)
    except IntegrityError as exc:
        if not is_idempotency_violation(exc):
            raise
        # begin() already rolled the transaction back. Drop the unsaved objects so
        # the lookup below cannot flush them again.
        await session.rollback()
        session.expunge_all()
        existing = await _get_by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            logger.info(
                "idempotency conflict key=%s existing_payment_id=%s",
                idempotency_key,
                existing.id,
            )
            raise IdempotencyConflict(existing.id) from None
        logger.info("idempotent replay key=%s payment_id=%s", idempotency_key, existing.id)
        return existing

    logger.info(
        "payment created payment_id=%s amount=%s %s",
        payment.id,
        format_money(payment.amount),
        payment.currency,
    )
    return payment


async def get_payment(session: AsyncSession, payment_id: UUID) -> Payment | None:
    return await session.get(Payment, payment_id)


async def _get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> Payment | None:
    result = await session.scalars(select(Payment).where(Payment.idempotency_key == idempotency_key))
    return result.one_or_none()


def to_accepted(payment: Payment) -> PaymentAccepted:
    return PaymentAccepted(
        payment_id=payment.id,
        status=PaymentStatus(payment.status),
        created_at=payment.created_at,
    )


def to_detail(payment: Payment) -> PaymentDetail:
    return PaymentDetail(
        payment_id=payment.id,
        amount=payment.amount,
        currency=Currency(payment.currency),
        description=payment.description,
        metadata=dict(payment.metadata_ or {}),
        status=PaymentStatus(payment.status),
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        failure_reason=payment.failure_reason,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
