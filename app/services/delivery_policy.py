from datetime import datetime

from app.domain.enums import DeliveryStatus


def retry_delay_seconds(
    *,
    attempt_count: int,
    retry_limit: int,
    provider_retry_after: int | None,
) -> int | None:
    if attempt_count >= retry_limit:
        return None
    exponential = min(60 * 2 ** max(attempt_count - 1, 0), 6 * 60 * 60)
    return max(exponential, provider_retry_after or 0)


def is_claimable(
    status: DeliveryStatus, next_attempt_at: datetime, now: datetime
) -> bool:
    return (
        status in {DeliveryStatus.PENDING, DeliveryStatus.RETRYABLE}
        and next_attempt_at <= now
    )

