import asyncio
import logging
import random
from dataclasses import dataclass
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GatewayResult:
    succeeded: bool
    failure_reason: str | None = None


async def charge(payment_id: UUID) -> GatewayResult:
    """Emulate an external gateway: 2-5 seconds, 90% approval by default."""
    delay = random.uniform(settings.gateway_min_delay_seconds, settings.gateway_max_delay_seconds)
    logger.info("gateway started payment_id=%s delay=%.2fs", payment_id, delay)
    await asyncio.sleep(delay)

    if random.random() < settings.gateway_success_rate:
        logger.info("gateway approved payment_id=%s", payment_id)
        return GatewayResult(succeeded=True)

    logger.info("gateway declined payment_id=%s", payment_id)
    return GatewayResult(succeeded=False, failure_reason="gateway_declined")
