from datetime import UTC, datetime

import pytest

from app.utils.time import delivery_time_reached, local_date


def test_calendar_day_uses_configured_timezone() -> None:
    before_midnight_utc = datetime(2026, 7, 26, 21, 30, tzinfo=UTC)
    assert str(local_date(before_midnight_utc, "Europe/Moscow")) == "2026-07-27"


def test_delivery_time_is_evaluated_in_application_timezone() -> None:
    now = datetime(2026, 7, 26, 5, 1, tzinfo=UTC)
    assert delivery_time_reached(now, "Europe/Moscow", "08:00")
    assert not delivery_time_reached(now, "Europe/Moscow", "08:02")


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        local_date(datetime(2026, 7, 26), "Europe/Moscow")

