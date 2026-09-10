"""business_date derivation, including the midnight/cutoff boundary
(plan sections 9.2 and 24.2).

The scenario that motivates the whole module: the shop closes at 11pm and cashes
up at 00:30. That cash belongs to the day that earned it, not to the calendar
day the clock happens to show.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.dates import (
    COMPANY_TZ,
    DEFAULT_DAY_CUTOFF_HOUR,
    business_date_for,
    business_day_bounds,
    derive_business_date,
    to_company_time,
)


def colombo(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    """A wall-clock moment in the shop's timezone."""
    return datetime(y, m, d, hh, mm, tzinfo=COMPANY_TZ)


class TestCutoffBoundary:
    """Default cutoff is 02:00 local."""

    def test_the_cash_up_after_an_11pm_close(self) -> None:
        # 00:30 on the 8th is still the 7th's trading day.
        assert derive_business_date(colombo(2026, 9, 8, 0, 30)) == date(2026, 9, 7)

    @pytest.mark.parametrize(
        ("hour", "minute", "expected_day"),
        [
            (0, 0, 7),  # midnight exactly -> previous day
            (1, 59, 7),  # one minute before cutoff -> previous day
            (2, 0, 8),  # cutoff exactly -> current day
            (2, 1, 8),  # just after cutoff -> current day
            (23, 59, 8),  # late evening -> current day
        ],
    )
    def test_boundary_is_inclusive_at_the_cutoff_hour(
        self, hour: int, minute: int, expected_day: int
    ) -> None:
        moment = colombo(2026, 9, 8, hour, minute)
        assert derive_business_date(moment) == date(2026, 9, expected_day)

    def test_month_boundary(self) -> None:
        assert derive_business_date(colombo(2026, 10, 1, 1, 0)) == date(2026, 9, 30)

    def test_year_boundary(self) -> None:
        assert derive_business_date(colombo(2027, 1, 1, 0, 15)) == date(2026, 12, 31)


class TestConfigurableCutoff:
    def test_cutoff_zero_means_calendar_day(self) -> None:
        assert derive_business_date(colombo(2026, 9, 8, 0, 30), day_cutoff_hour=0) == date(
            2026, 9, 8
        )

    def test_later_cutoff_extends_the_trading_day(self) -> None:
        assert derive_business_date(colombo(2026, 9, 8, 4, 0), day_cutoff_hour=6) == date(2026, 9, 7)

    @pytest.mark.parametrize("bad", [-1, 24, 99])
    def test_invalid_cutoff_is_rejected(self, bad: int) -> None:
        with pytest.raises(ValueError, match="day_cutoff_hour"):
            derive_business_date(colombo(2026, 9, 8, 12), day_cutoff_hour=bad)


class TestTimezoneHandling:
    """Storage is UTC; interpretation is Asia/Colombo (UTC+5:30)."""

    def test_utc_input_is_converted_before_the_cutoff_is_applied(self) -> None:
        # 19:30 UTC on the 7th == 01:00 Colombo on the 8th, which is before the
        # 02:00 cutoff, so it belongs to the 7th.
        utc_moment = datetime(2026, 9, 7, 19, 30, tzinfo=timezone.utc)
        assert to_company_time(utc_moment).hour == 1
        assert derive_business_date(utc_moment) == date(2026, 9, 7)

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        naive = datetime(2026, 9, 7, 19, 30)
        aware = datetime(2026, 9, 7, 19, 30, tzinfo=timezone.utc)
        assert derive_business_date(naive) == derive_business_date(aware)

    def test_utc_and_colombo_can_disagree_about_the_calendar_day(self) -> None:
        # 21:00 UTC on the 7th is already 02:30 on the 8th in Colombo, past the
        # cutoff — so the business date is the 8th even though it is still the
        # 7th in UTC.
        utc_moment = datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc)
        assert utc_moment.date() == date(2026, 9, 7)
        assert derive_business_date(utc_moment) == date(2026, 9, 8)


class TestBusinessDateFor:
    """The page's designated date column wins over the derived value."""

    def test_date_column_takes_precedence(self) -> None:
        occurred = colombo(2026, 9, 8, 14, 0)
        assert business_date_for(occurred, date_column_value=date(2026, 9, 1)) == date(2026, 9, 1)

    def test_falls_back_to_derivation_when_no_date_column(self) -> None:
        occurred = colombo(2026, 9, 8, 0, 30)
        assert business_date_for(occurred, date_column_value=None) == date(2026, 9, 7)


class TestBusinessDayBounds:
    """The inverse of derive_business_date."""

    def test_bounds_are_a_half_open_24_hour_window(self) -> None:
        start, end = business_day_bounds(date(2026, 9, 7))
        assert (end - start).total_seconds() == 24 * 3600
        assert to_company_time(start).hour == DEFAULT_DAY_CUTOFF_HOUR

    def test_every_instant_in_the_window_maps_back_to_the_same_date(self) -> None:
        target = date(2026, 9, 7)
        start, end = business_day_bounds(target)
        assert derive_business_date(start) == target
        # `end` is exclusive: it belongs to the next business date.
        assert derive_business_date(end) == date(2026, 9, 8)

    def test_windows_tile_without_gap_or_overlap(self) -> None:
        _, first_end = business_day_bounds(date(2026, 9, 7))
        second_start, _ = business_day_bounds(date(2026, 9, 8))
        assert first_end == second_start
