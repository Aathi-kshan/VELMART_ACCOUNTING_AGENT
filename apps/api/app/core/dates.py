"""Business dates and time handling (plan section 9.2).

Four timestamps, each with a job:

    occurred_at    when the business event happened      TIMESTAMPTZ
    business_date  the accounting day it belongs to      DATE
    created_at     when it was entered into the system   TIMESTAMPTZ
    updated_at     when it was last changed              TIMESTAMPTZ

Everything is stored in UTC and rendered in Asia/Colombo.

`business_date` is derived **server-side**, never taken from the client. A shop
that closes at 11pm and cashes up at 00:30 posts that cash to the *previous*
business date — getting this wrong is the most common source of "the numbers
don't match" in retail software, which is why the cutoff lives here rather than
being reimplemented per caller.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

#: The shop's wall clock. Storage is UTC; this is only for interpretation.
COMPANY_TZ = ZoneInfo("Asia/Colombo")

#: Entries before this local hour belong to the previous business date.
DEFAULT_DAY_CUTOFF_HOUR = 2


def utc_now() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(timezone.utc)


def to_company_time(moment: datetime, tz: ZoneInfo = COMPANY_TZ) -> datetime:
    """Convert an instant to the shop's local wall clock.

    A naive datetime is assumed to be UTC: everything crossing our boundaries is
    UTC, and guessing 'local' for a naive value is how off-by-one-day bugs start.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz)


def derive_business_date(
    occurred_at: datetime,
    *,
    day_cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR,
    tz: ZoneInfo = COMPANY_TZ,
) -> date:
    """The accounting day an event belongs to.

    Local time before `day_cutoff_hour` counts as the previous business date, so
    the 00:30 cash-up after an 11pm close lands on the day that earned it.
    """
    if not 0 <= day_cutoff_hour <= 23:
        raise ValueError(f"day_cutoff_hour must be 0-23, got {day_cutoff_hour}")

    local = to_company_time(occurred_at, tz)
    if local.hour < day_cutoff_hour:
        return (local - timedelta(days=1)).date()
    return local.date()


def business_date_for(
    occurred_at: datetime,
    *,
    date_column_value: date | None = None,
    day_cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR,
    tz: ZoneInfo = COMPANY_TZ,
) -> date:
    """Resolve `business_date` the way the record write path must.

    The page's designated date column wins when the Owner set one
    (`pages.date_column_key`); otherwise fall back to `occurred_at` and the
    company's cutoff hour.
    """
    if date_column_value is not None:
        return date_column_value
    return derive_business_date(occurred_at, day_cutoff_hour=day_cutoff_hour, tz=tz)


def business_day_bounds(
    business_date: date,
    *,
    day_cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR,
    tz: ZoneInfo = COMPANY_TZ,
) -> tuple[datetime, datetime]:
    """The UTC half-open interval `[start, end)` covered by a business date.

    The inverse of `derive_business_date`, for querying by instant rather than
    by the stored `business_date` column.
    """
    start_local = datetime.combine(business_date, time(day_cutoff_hour), tzinfo=tz)
    end_local = datetime.combine(business_date + timedelta(days=1), time(day_cutoff_hour), tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
