"""Money handling — the single definition (plan section 9.1).

Rules this module exists to enforce:

* `Decimal` everywhere in Python; `NUMERIC(14,2)` in Postgres; a **string** on
  the wire and inside JSONB — never a JSON number, which most parsers widen to
  a double.
* Rounding is half-up to two decimals, defined **once**, here.
* A `float` is never accepted. Passing one raises rather than silently losing
  precision three steps later, when the number is already in the database.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Business money is NUMERIC(14,2): 12 digits before the point, 2 after.
MONEY_PLACES = Decimal("0.01")
MAX_MONEY = Decimal("99999999999.99")
MIN_MONEY = Decimal("-99999999999.99")


class MoneyError(ValueError):
    """Raised when a value cannot be treated as money."""


def parse_money(value: str | int | Decimal) -> Decimal:
    """Parse a money value into a quantised `Decimal`.

    Accepts a string (the wire format), an int, or a Decimal. **Rejects float**
    — `0.1 + 0.2` is not `0.3`, and money that has been through a float cannot
    be trusted afterwards.
    """
    if isinstance(value, float):
        raise MoneyError(
            "float is not accepted for money; pass a string such as '35000.00'. "
            "Floating point silently corrupts currency values."
        )
    if isinstance(value, bool):  # bool is an int subclass; never money
        raise MoneyError("bool is not a money value")

    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise MoneyError("empty string is not a money value")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise MoneyError(f"{value!r} is not a valid money value") from exc
    else:
        raise MoneyError(f"cannot parse {type(value).__name__} as money")

    if not parsed.is_finite():
        raise MoneyError("money must be finite (not NaN or Infinity)")

    quantised = quantize_money(parsed)
    if quantised > MAX_MONEY or quantised < MIN_MONEY:
        raise MoneyError(f"money value {quantised} is out of range for NUMERIC(14,2)")
    return quantised


def quantize_money(value: Decimal) -> Decimal:
    """Round to two decimal places, half-up.

    Half-up, not Python's default banker's rounding: 0.005 becomes 0.01, which
    is what a shopkeeper checking the arithmetic by hand expects.
    """
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def format_money(value: Decimal) -> str:
    """Render for the wire: always two decimals, always a string."""
    return f"{quantize_money(value):f}"
