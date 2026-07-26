from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_date(now: datetime, timezone_name: str) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(timezone_name)).date()


def delivery_time_reached(now: datetime, timezone_name: str, configured_time: str) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    hour, minute = (int(part) for part in configured_time.split(":"))
    local_now = now.astimezone(ZoneInfo(timezone_name))
    return local_now.time() >= time(hour=hour, minute=minute)

