"""Business dates and time (plan section 9.2).

Four timestamps, each with a job:

    occurred_at    when the business event happened      TIMESTAMPTZ
    business_date  the accounting day it belongs to      DATE
    created_at     when it was entered into the system   TIMESTAMPTZ
    updated_at     when it was last changed              TIMESTAMPTZ

Everything is stored in UTC and rendered in Asia/Colombo.

The rule that matters: a shop closing at 11pm and cashing up at 12:30am must
post that cash to the **previous** business date. Section 9.2 calls getting this
wrong "the most common source of 'the numbers don't match' in retail software".
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

#: The shop's wall clock. Sri Lanka is UTC+5:30 year round — no DST.
COMPANY_TIMEZONE = "Asia/Colombo"

#: Entries before this local hour count as the previous business day
#: (company_settings.day_cutoff_hour; 02:00 default per plan section 8.2).
DEFAULT_DAY_CUTOFF_HOUR = 2


def now_utc() -> datetime:
    """The current instant, timezone-aware, in UTC."""
    return datetime.now(tz=UTC)


def to_company_time(moment: datetime, tz: str = COMPANY_TIMEZONE) -> datetime:
    """Render a UTC instant in the company's local timezone.

    A naive datetime is assumed to be UTC: everything this system stores is
    UTC, so a missing tzinfo means "not yet localised", never "local time".
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(tz))


def business_date_for(
    occurred_at: datetime,
    *,
    cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR,
    tz: str = COMPANY_TIMEZONE,
) -> date:
    """The accounting day an event belongs to.

    Local time is what the shopkeeper means by "today", so the instant is first
    converted to the company timezone. Anything before `cutoff_hour` belongs to
    the previous day — the 12:30am cash-up after an 11pm close.

    >>> business_date_for(datetime(2026, 9, 8, 17, 30, tzinfo=timezone.utc))
    datetime.date(2026, 9, 8)
    >>> # 00:30 Colombo on the 9th == 19:00 UTC on the 8th -> previous day
    >>> business_date_for(datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc))
    datetime.date(2026, 9, 8)
    """
    if not 0 <= cutoff_hour <= 23:
        raise ValueError(f"cutoff_hour must be 0-23, got {cutoff_hour}")

    local = to_company_time(occurred_at, tz)
    if local.hour < cutoff_hour:
        return (local - timedelta(days=1)).date()
    return local.date()
