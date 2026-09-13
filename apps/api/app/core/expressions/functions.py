"""The formula/`page_validations` function library (plan section 11.1, P4
§2). `FORMULA_FUNCTIONS` is the single source of truth both `parser.py`
(which `Call` names are legal) and `evaluator.py`/`sql_compiler.py` (what
they actually do) import — the allowed list and the implemented list can
never drift apart because there is only one list.

Everything here operates in `Decimal`, never `float` (the project's own
working agreement) — `round` uses `ROUND_HALF_UP`, matching
`app/core/money.py`'s existing convention, never banker's rounding.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.dates import now_utc, to_company_time


def fn_sum(*args: Decimal) -> Decimal:
    """Variadic over its arguments (`sum(basic, ot, bonus)`) — not Python's
    iterable-`sum`, which this whitelist never exposes."""
    total = Decimal(0)
    for arg in args:
        total += arg
    return total


def fn_min(*args: Decimal) -> Decimal:
    return min(args)


def fn_max(*args: Decimal) -> Decimal:
    return max(args)


def fn_round(value: Decimal, ndigits: int = 0) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-ndigits), rounding=ROUND_HALF_UP)


def fn_abs(value: Decimal) -> Decimal:
    return abs(value)


def fn_safe_div(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal(0)) -> Decimal:
    """Returns `default` on a zero denominator instead of raising — this is
    *why* raw `/` and `safe_div` coexist in the grammar: `/` is for
    divisions that are structurally safe, `safe_div` for ones that might
    not be (`safe_div(revenue - cogs, revenue)`, where `revenue` could
    legitimately be zero some days)."""
    if denominator == 0:
        return default
    return numerator / denominator


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def fn_days_between(start: date | datetime, end: date | datetime) -> Decimal:
    """Returns a `Decimal`, never a bare `int`, so it composes with other
    arithmetic (`Days Overdue = days_between(due_date, today())`) without a
    type-mixing surprise."""
    return Decimal((_as_date(end) - _as_date(start)).days)


def fn_today() -> date:
    """Company-local "today" — reusing `app/core/dates.py`'s `now_utc()` +
    `to_company_time()`, **not** naive UTC-today, for the same
    midnight-boundary reason `business_date_for` exists."""
    return to_company_time(now_utc()).date()


def fn_coalesce(*args: Any) -> Any:
    """First non-`None` argument, SQL-style."""
    for arg in args:
        if arg is not None:
            return arg
    return None


FORMULA_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sum": fn_sum,
    "min": fn_min,
    "max": fn_max,
    "round": fn_round,
    "abs": fn_abs,
    "safe_div": fn_safe_div,
    "days_between": fn_days_between,
    "today": fn_today,
    "coalesce": fn_coalesce,
}
