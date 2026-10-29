from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.config import settings
from app.dto import PaymentSnapshot
from app.exceptions import WebhookDeliveryError
from app.services.webhook import deliver


def _snapshot(**overrides) -> PaymentSnapshot:
    data = dict(
        payment_id=uuid4(),
        amount=Decimal("10.50"),
        currency="RUB",
        description="order",
        metadata={"order_id": "1"},
        status="succeeded",
        webhook_url="http://merchant.test/hook",
        created_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
        processed_at=datetime(2026, 10, 29, 0, 1, tzinfo=timezone.utc),
        failure_reason=None,
    )
    data.update(overrides)
    return PaymentSnapshot(**data)


def test_webhook_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_max_attempts", 3)
    monkeypatch.setattr(settings, "webhook_backoff_seconds", 0)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="later")
        return httpx.Response(204)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await deliver(_snapshot(), client=client)

    import asyncio

    asyncio.run(run())
    assert calls["n"] == 3


def test_webhook_gives_up_after_three_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_max_attempts", 3)
    monkeypatch.setattr(settings, "webhook_backoff_seconds", 0)
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="down")

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(WebhookDeliveryError):
                await deliver(_snapshot(), client=client)

    import asyncio

    asyncio.run(run())
    assert calls["n"] == 3
