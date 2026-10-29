import asyncio
import logging

import httpx

from app.config import settings
from app.dto import PaymentSnapshot
from app.exceptions import WebhookDeliveryError
from app.money import format_money

logger = logging.getLogger(__name__)


def webhook_body(payment: PaymentSnapshot) -> dict:
    return {
        "event": "payment.processed",
        "payment_id": str(payment.payment_id),
        "status": payment.status,
        "amount": format_money(payment.amount),
        "currency": payment.currency,
        "description": payment.description,
        "metadata": payment.metadata,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at.isoformat(),
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }


async def deliver(payment: PaymentSnapshot, *, client: httpx.AsyncClient | None = None) -> None:
    """POST the result. Retries with exponential backoff, then raises.

    Delays between attempts are backoff, backoff*2, ... The last failure is not
    followed by a sleep. The caller decides whether the whole message is retried.
    """
    body = webhook_body(payment)
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.webhook_timeout_seconds)
    delay = settings.webhook_backoff_seconds
    last_error: Exception | None = None

    try:
        for attempt in range(1, settings.webhook_max_attempts + 1):
            try:
                response = await http.post(
                    payment.webhook_url,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "payment-service/1.0",
                        "X-Payment-Id": str(payment.payment_id),
                        "X-Payment-Event": "payment.processed",
                    },
                )
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if 200 <= response.status_code < 300:
                    logger.info(
                        "webhook delivered payment_id=%s attempt=%s status=%s",
                        payment.payment_id,
                        attempt,
                        response.status_code,
                    )
                    return
                snippet = response.text[:300].replace("\n", " ")
                last_error = WebhookDeliveryError(
                    f"status={response.status_code} body={snippet}"
                )

            logger.warning(
                "webhook failed payment_id=%s attempt=%s/%s error=%s",
                payment.payment_id,
                attempt,
                settings.webhook_max_attempts,
                last_error,
            )
            if attempt < settings.webhook_max_attempts and delay > 0:
                await asyncio.sleep(delay)
                delay *= 2
    finally:
        if owns_client:
            await http.aclose()

    raise WebhookDeliveryError(
        f"webhook failed after {settings.webhook_max_attempts} attempts: {last_error}"
    ) from last_error
