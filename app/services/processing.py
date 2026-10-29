import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update

from app.db import SessionFactory
from app.dto import PaymentSnapshot
from app.enums import PaymentStatus
from app.exceptions import PaymentNotFound
from app.models import Payment
from app.services.gateway import charge
from app.services.webhook import deliver

logger = logging.getLogger(__name__)


async def process_payment(payment_id: UUID) -> None:
    """Settle a still-pending payment, then notify the webhook.

    The gateway runs outside a database transaction. The status update is
    conditional on `pending`, so a duplicate delivery does not charge twice
    and does not overwrite a terminal status. A failed webhook is raised to
    the caller: the message is retried, the gateway is not.
    """
    snapshot = await _load(payment_id)
    if snapshot is None:
        raise PaymentNotFound(payment_id)

    if snapshot.status == PaymentStatus.PENDING.value:
        result = await charge(payment_id)
        snapshot = await _finish(payment_id, result.succeeded, result.failure_reason)
        if snapshot is None:
            raise PaymentNotFound(payment_id)

    await deliver(snapshot)


async def _load(payment_id: UUID) -> PaymentSnapshot | None:
    async with SessionFactory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return None
        return _snapshot(payment)


async def _finish(
    payment_id: UUID,
    succeeded: bool,
    failure_reason: str | None,
) -> PaymentSnapshot | None:
    now = datetime.now(timezone.utc)
    new_status = PaymentStatus.SUCCEEDED.value if succeeded else PaymentStatus.FAILED.value
    async with SessionFactory() as session:
        updated = await session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING.value)
            .values(
                status=new_status,
                processed_at=now,
                failure_reason=failure_reason,
            )
            .returning(Payment.id)
        )
        won = updated.scalar_one_or_none() is not None
        await session.commit()
        payment = await session.get(Payment, payment_id)

    if payment is None:
        return None
    if won:
        logger.info(
            "payment settled payment_id=%s status=%s",
            payment_id,
            payment.status,
        )
    else:
        logger.info(
            "payment already settled payment_id=%s status=%s",
            payment_id,
            payment.status,
        )
    return _snapshot(payment)


def _snapshot(payment: Payment) -> PaymentSnapshot:
    return PaymentSnapshot(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=dict(payment.metadata_ or {}),
        status=payment.status,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
        failure_reason=payment.failure_reason,
    )
