"""The midnight cash-up must land on the right accounting day (plan section 9.2).

Colombo is UTC+5:30 with no daylight saving, so every expected value below is
the UTC instant plus 5h30m.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.dates import business_date_for, to_company_time


def utc(y: int, m: int, d: int, hour: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, hour, minute, tzinfo=UTC)


class TestCutoffBoundary:
    """The 02:00 default cutoff, exercised either side of the line."""

    def test_evening_trading_is_same_day(self) -> None:
        # 17:30 UTC == 23:00 Colombo, the shop closing
        assert business_date_for(utc(2026, 9, 8, 17, 30)) == date(2026, 9, 8)

    def test_after_midnight_cash_up_is_previous_day(self) -> None:
        # 19:00 UTC == 00:30 Colombo on the 9th — the cash-up after an 11pm
        # close. It belongs to the 8th's takings.
        assert business_date_for(utc(2026, 9, 8, 19, 0)) == date(2026, 9, 8)

    def test_one_minute_before_cutoff_is_previous_day(self) -> None:
        # 20:29 UTC == 01:59 Colombo
        assert business_date_for(utc(2026, 9, 8, 20, 29)) == date(2026, 9, 8)

    def test_exactly_at_cutoff_is_the_new_day(self) -> None:
        # 20:30 UTC == 02:00 Colombo — the boundary is inclusive of the new day
        assert business_date_for(utc(2026, 9, 8, 20, 30)) == date(2026, 9, 9)

    def test_morning_is_the_new_day(self) -> None:
        # 03:30 UTC == 09:00 Colombo
        assert business_date_for(utc(2026, 9, 9, 3, 30)) == date(2026, 9, 9)


class TestConfigurableCutoff:
    def test_zero_cutoff_means_calendar_day(self) -> None:
        # With no cutoff, 00:30 Colombo is simply the 9th
        assert business_date_for(utc(2026, 9, 8, 19, 0), cutoff_hour=0) == date(2026, 9, 9)

    def test_late_cutoff_extends_the_business_day(self) -> None:
        # A 6am cutoff: 05:00 Colombo still belongs to the previous day
        assert business_date_for(utc(2026, 9, 8, 23, 30), cutoff_hour=6) == date(2026, 9, 8)

    @pytest.mark.parametrize("bad", [-1, 24, 99])
    def test_invalid_cutoff_rejected(self, bad: int) -> None:
        with pytest.raises(ValueError, match="cutoff_hour"):
            business_date_for(utc(2026, 9, 8, 12), cutoff_hour=bad)


class TestTimezoneHandling:
    def test_colombo_offset_is_five_thirty(self) -> None:
        local = to_company_time(utc(2026, 9, 8, 12, 0))
        assert (local.hour, local.minute) == (17, 30)

    def test_offset_holds_in_january_too(self) -> None:
        # Sri Lanka has no DST; the offset must not shift with the season.
        local = to_company_time(utc(2026, 1, 8, 12, 0))
        assert (local.hour, local.minute) == (17, 30)

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        naive = datetime(2026, 9, 8, 19, 0)  # noqa: DTZ001 - deliberate
        assert business_date_for(naive) == business_date_for(utc(2026, 9, 8, 19, 0))


class TestMonthAndYearBoundaries:
    def test_crosses_month_end(self) -> None:
        # 19:00 UTC on 31 Aug == 00:30 Colombo on 1 Sep -> back to 31 Aug
        assert business_date_for(utc(2026, 8, 31, 19, 0)) == date(2026, 8, 31)

    def test_crosses_year_end(self) -> None:
        assert business_date_for(utc(2026, 12, 31, 19, 0)) == date(2026, 12, 31)
