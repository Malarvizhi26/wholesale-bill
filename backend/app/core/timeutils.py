"""Shop-local (India Standard Time) date helpers.

All business-day boundaries ("today", daily sales, cash drawer day, ageing as-of) are computed
in Asia/Kolkata, not UTC. Timestamps are still stored in UTC.

Windows installs often lack the IANA tz database (no `tzdata` package), so we fall back to a
fixed +05:30 offset. India has no daylight saving, so the fallback is exact.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

try:  # pragma: no cover - depends on the host tz database
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
except Exception:  # ZoneInfoNotFoundError / ImportError
    IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    """Current business date in India."""
    return now_ist().date()


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise a timestamp to aware UTC. Naive values are treated as UTC (how they are stored)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_ist(dt: datetime) -> datetime:
    """Convert a stored timestamp (aware, or naive-UTC as read back from SQLite) to IST."""
    return to_utc(dt).astimezone(IST)


def ist_date_of(dt: datetime) -> date:
    """Business (IST) date of a timestamp - used for ledger entry_date."""
    return to_ist(dt).date()


def ist_day_bounds_utc(start: date, end: Optional[date] = None) -> Tuple[datetime, datetime]:
    """[start 00:00 IST, (end + 1 day) 00:00 IST) as aware UTC datetimes (end is exclusive)."""
    end = end or start
    start_dt = datetime.combine(start, time.min, tzinfo=IST).astimezone(timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=IST).astimezone(timezone.utc)
    return start_dt, end_dt
