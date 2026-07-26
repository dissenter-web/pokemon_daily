from datetime import UTC, datetime, timedelta

from app.domain.enums import DeliveryStatus
from app.services.delivery_policy import is_claimable, retry_delay_seconds


def test_safe_failure_retries_with_exponential_backoff() -> None:
    assert retry_delay_seconds(
        attempt_count=1, retry_limit=4, provider_retry_after=None
    ) == 60
    assert retry_delay_seconds(
        attempt_count=2, retry_limit=4, provider_retry_after=180
    ) == 180


def test_retry_limit_stops_background_restarts() -> None:
    assert (
        retry_delay_seconds(
            attempt_count=4, retry_limit=4, provider_retry_after=None
        )
        is None
    )


def test_only_pending_or_retryable_due_delivery_can_be_claimed() -> None:
    now = datetime(2026, 7, 26, tzinfo=UTC)
    assert is_claimable(DeliveryStatus.PENDING, now, now)
    assert is_claimable(DeliveryStatus.RETRYABLE, now - timedelta(seconds=1), now)
    assert not is_claimable(DeliveryStatus.SENT, now, now)
    assert not is_claimable(
        DeliveryStatus.RETRYABLE, now + timedelta(seconds=1), now
    )

