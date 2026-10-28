from uuid import UUID


class IdempotencyConflict(Exception):
    """The same Idempotency-Key was sent with a different request body."""

    def __init__(self, payment_id: UUID) -> None:
        self.payment_id = payment_id
        super().__init__(
            f"idempotency key already used for a different request, payment_id={payment_id}"
        )


class PermanentProcessingError(Exception):
    """A failure that will not succeed on retry. The message goes straight to the DLQ."""


class PaymentNotFound(PermanentProcessingError):
    def __init__(self, payment_id: UUID) -> None:
        self.payment_id = payment_id
        super().__init__(f"payment {payment_id} does not exist")


class WebhookDeliveryError(Exception):
    """The webhook was not accepted after all HTTP attempts."""
