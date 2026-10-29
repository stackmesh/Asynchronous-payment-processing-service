from collections.abc import Mapping
from typing import Any


def current_attempt(headers: Mapping[str, Any] | None) -> int:
    """1-based processing attempt. `x-retry-count` is how many attempts already failed."""
    raw = (headers or {}).get("x-retry-count", 0)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        failed_before = int(raw)
    except (TypeError, ValueError):
        failed_before = 0
    return max(failed_before, 0) + 1


def failure_destination(attempt: int, max_attempts: int) -> str:
    """Where a failed attempt goes: another try, or the dead-letter queue."""
    if attempt >= max_attempts:
        return "dlq"
    return "retry"


def retry_ttl_ms(failed_attempt: int) -> int:
    """Exponential delay before the next delivery: 2s, 4s, 8s, ..."""
    return (2 ** failed_attempt) * 1000


def retry_queue_name(failed_attempt: int) -> str:
    return f"payments.retry.{failed_attempt}"


def sanitize_header(value: str, limit: int = 200) -> str:
    return " ".join(value.split())[:limit]


def retry_headers(failed_attempt: int, error: BaseException) -> dict[str, int | str]:
    return {
        "x-retry-count": failed_attempt,
        "x-last-error": sanitize_header(str(error)),
    }
