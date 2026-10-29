from app.db import Base
from app.models import OutboxEvent, Payment


def test_schema_contains_payments_and_outbox() -> None:
    assert set(Base.metadata.tables) == {"payments", "outbox"}
    payment_columns = {column.name for column in Payment.__table__.columns}
    outbox_columns = {column.name for column in OutboxEvent.__table__.columns}
    assert {"idempotency_key", "metadata", "webhook_url", "processed_at"} <= payment_columns
    assert {"payload", "published_at", "next_attempt_at", "attempts"} <= outbox_columns
