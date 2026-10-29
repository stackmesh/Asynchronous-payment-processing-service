from decimal import Decimal

from app.idempotency import canonical_request_hash, is_idempotency_violation


def _hash(**overrides) -> str:
    data = dict(
        amount=Decimal("10.5"),
        currency="RUB",
        description="order",
        metadata={"b": 1, "a": {"z": 2, "y": 1}},
        webhook_url="https://merchant.example/hook",
    )
    data.update(overrides)
    return canonical_request_hash(**data)


def test_hash_ignores_key_order_and_trailing_zeros() -> None:
    again = _hash(amount=Decimal("10.50"), metadata={"a": {"y": 1, "z": 2}, "b": 1})
    assert _hash() == again


def test_hash_changes_when_the_body_changes() -> None:
    assert _hash() != _hash(amount=Decimal("10.51"))
    assert _hash() != _hash(webhook_url="https://merchant.example/other")


def test_idempotency_violation_matches_only_our_constraint() -> None:
    class Orig(Exception):
        def __init__(self, sqlstate: str, constraint_name: str) -> None:
            self.sqlstate = sqlstate
            self.constraint_name = constraint_name

    class Exc(Exception):
        def __init__(self, orig: Orig) -> None:
            self.orig = orig

    match = Exc(Orig("23505", "uq_payments_idempotency_key"))
    other = Exc(Orig("23505", "uq_outbox_aggregate_event"))
    check = Exc(Orig("23514", "ck_payments_amount_positive"))

    assert is_idempotency_violation(match) is True  # type: ignore[arg-type]
    assert is_idempotency_violation(other) is False  # type: ignore[arg-type]
    assert is_idempotency_violation(check) is False  # type: ignore[arg-type]
