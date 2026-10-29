from app.messaging.retry import (
    current_attempt,
    failure_destination,
    retry_queue_name,
    retry_ttl_ms,
)


def test_attempt_counter_starts_at_one() -> None:
    assert current_attempt(None) == 1
    assert current_attempt({}) == 1
    assert current_attempt({"x-retry-count": 0}) == 1
    assert current_attempt({"x-retry-count": "2"}) == 3
    assert current_attempt({"x-retry-count": b"1"}) == 2


def test_three_attempts_then_dlq() -> None:
    assert failure_destination(1, 3) == "retry"
    assert failure_destination(2, 3) == "retry"
    assert failure_destination(3, 3) == "dlq"
    assert retry_ttl_ms(1) == 2_000
    assert retry_ttl_ms(2) == 4_000
    assert retry_queue_name(1) == "payments.retry.1"
    assert retry_queue_name(2) == "payments.retry.2"
