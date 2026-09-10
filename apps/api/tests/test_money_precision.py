"""Money precision (plan section 24.2, 'Financial correctness and data integrity').

The property under test: a money value survives the round trip without ever
becoming a float.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import (
    MoneyError,
    format_money,
    money_or_none,
    parse_money,
    quantize_money,
)


class TestFloatIsRefused:
    """The whole point of the module: no float, ever."""

    @pytest.mark.parametrize("value", [1.0, 0.1, 35000.50, -2.5])
    def test_float_input_is_rejected(self, value: float) -> None:
        with pytest.raises(MoneyError, match="float"):
            parse_money(value)

    def test_the_classic_float_error_cannot_get_in(self) -> None:
        # 0.1 + 0.2 == 0.30000000000000004 as a float. Passed as a string it is
        # exact; passed as a float it is refused outright.
        assert parse_money("0.30") == Decimal("0.30")
        with pytest.raises(MoneyError):
            parse_money(0.1 + 0.2)

    def test_bool_is_not_money(self) -> None:
        with pytest.raises(MoneyError):
            parse_money(True)


class TestParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("35000.00", "35000.00"),
            ("35000", "35000.00"),
            ("  1234.5  ", "1234.50"),
            ("-99.99", "-99.99"),
            ("0", "0.00"),
            (50000, "50000.00"),
            (Decimal("175000.005"), "175000.01"),
        ],
    )
    def test_accepts_strings_ints_decimals(self, raw: object, expected: str) -> None:
        assert parse_money(raw) == Decimal(expected)

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "1,234.00", "Rs.500", None, [], "NaN"])
    def test_rejects_junk(self, raw: object) -> None:
        with pytest.raises(MoneyError):
            parse_money(raw)

    def test_infinity_is_rejected(self) -> None:
        with pytest.raises(MoneyError):
            parse_money(Decimal("Infinity"))


class TestRounding:
    """Half-up, because that is what a hand-checked ledger expects."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.005", "0.01"),  # banker's rounding would give 0.00
            ("0.015", "0.02"),  # banker's rounding would give 0.02 too
            ("0.025", "0.03"),  # banker's rounding would give 0.02
            ("2.675", "2.68"),
            ("-0.005", "-0.01"),
        ],
    )
    def test_half_up_not_bankers(self, raw: str, expected: str) -> None:
        assert quantize_money(Decimal(raw)) == Decimal(expected)


class TestNumericBounds:
    """NUMERIC(14,2): twelve digits before the point, two after."""

    def test_largest_representable_value(self) -> None:
        assert parse_money("999999999999.99") == Decimal("999999999999.99")

    @pytest.mark.parametrize("raw", ["1000000000000.00", "-1000000000000.00"])
    def test_overflow_is_rejected(self, raw: str) -> None:
        with pytest.raises(MoneyError):
            parse_money(raw)


class TestWireFormat:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("35000", "35000.00"), ("0", "0.00"), ("-12.5", "-12.50")],
    )
    def test_always_two_decimals_as_string(self, raw: str, expected: str) -> None:
        formatted = format_money(Decimal(raw))
        assert formatted == expected
        assert isinstance(formatted, str)

    def test_no_scientific_notation(self) -> None:
        # Decimal("1E+3") formats as "1000.00", not "1E+3" — JSON consumers and
        # humans both need the plain form.
        assert format_money(Decimal("1E+3")) == "1000.00"

    def test_round_trips_through_the_wire_format(self) -> None:
        original = Decimal("587400.37")
        assert parse_money(format_money(original)) == original


class TestOptional:
    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_becomes_none(self, empty: object) -> None:
        assert money_or_none(empty) is None

    def test_value_still_parses(self) -> None:
        assert money_or_none("12.34") == Decimal("12.34")
