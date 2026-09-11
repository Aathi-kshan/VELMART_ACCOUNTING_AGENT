"""Money must survive the round trip without losing a cent (plan section 9.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import MoneyError, format_money, parse_money, quantize_money


class TestFloatIsRejected:
    """The rule the whole module exists for."""

    def test_float_raises(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            parse_money(0.1)  # type: ignore[arg-type]

    def test_float_that_looks_exact_still_raises(self) -> None:
        # 35000.0 is representable, but accepting it establishes the habit.
        with pytest.raises(MoneyError):
            parse_money(35000.0)  # type: ignore[arg-type]

    def test_bool_is_not_money(self) -> None:
        with pytest.raises(MoneyError):
            parse_money(True)  # type: ignore[arg-type]


class TestRounding:
    """Half-up, not banker's rounding."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.005", "0.01"),  # banker's rounding would give 0.00
            ("0.015", "0.02"),  # ...and 0.02 here, so this one agrees
            ("0.025", "0.03"),  # banker's would give 0.02
            ("2.675", "2.68"),  # the classic float example: 2.67 in binary
            ("-0.005", "-0.01"),
        ],
    )
    def test_half_up(self, raw: str, expected: str) -> None:
        assert parse_money(raw) == Decimal(expected)

    def test_quantize_is_idempotent(self) -> None:
        once = quantize_money(Decimal("12.345"))
        assert quantize_money(once) == once


class TestPrecision:
    def test_large_amount_keeps_every_digit(self) -> None:
        # The value section 9.1 warns Dart's double turns into 812,399.99
        assert parse_money("812400.00") == Decimal("812400.00")

    def test_sum_of_thirds_does_not_drift(self) -> None:
        total = sum((parse_money("0.01") for _ in range(100)), Decimal(0))
        assert total == Decimal("1.00")

    def test_wire_format_always_two_places(self) -> None:
        assert format_money(Decimal("35000")) == "35000.00"
        assert format_money(Decimal("35000.5")) == "35000.50"

    def test_string_round_trip(self) -> None:
        original = "1234567.89"
        assert format_money(parse_money(original)) == original


class TestRejections:
    @pytest.mark.parametrize("raw", ["", "   ", "abc", "12.34.56", "1,234.00"])
    def test_invalid_strings(self, raw: str) -> None:
        with pytest.raises(MoneyError):
            parse_money(raw)

    @pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite(self, raw: str) -> None:
        with pytest.raises(MoneyError, match="finite"):
            parse_money(raw)

    def test_out_of_range_for_numeric_14_2(self) -> None:
        with pytest.raises(MoneyError, match="out of range"):
            parse_money("1000000000000.00")
