from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.config import settings


def site_tz():
    """Return the configured site timezone with graceful IST fallback on Windows."""
    try:
        return ZoneInfo(settings.site_timezone)
    except (ZoneInfoNotFoundError, Exception):
        if settings.site_timezone in ("Asia/Kolkata", "Asia/Calcutta", "IST"):
            return timezone(timedelta(hours=5, minutes=30), name="IST")
        return timezone.utc



def now_local() -> datetime:
    """Current wall-clock datetime in the site timezone."""
    return datetime.now(site_tz())


def today_local() -> date:
    """Current business date in the site timezone."""
    return now_local().date()


def minutes_elapsed(since: datetime) -> float:
    """Minutes elapsed since *since* (timezone-aware or assumed site tz)."""
    current = now_local()
    if since.tzinfo is None:
        since = since.replace(tzinfo=site_tz())
    return (current - since).total_seconds() / 60.0
