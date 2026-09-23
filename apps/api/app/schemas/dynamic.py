"""The runtime Pydantic model built from `page_columns` — plan section 3.4,
"the heart of validation". One model per page, built fresh from its current
columns on every request (columns can change at any time; nothing here is
cached across requests).

Scope boundary (see the P3 plan's Context section): `FORMULA` columns are
computed server-side and never accepted as input — the expression evaluator
itself is P4 (`app/core/expressions/`). `ATTACHMENT` columns are also
excluded from this model in P3: there is no upload mechanism yet
(attachments were deferred), so there is nothing a
client could legitimately supply for one yet. Both are simply absent from
the generated model — not validated, not accepted, not required.

`RECORD_REF`/`STORE_REF`/`USER_REF` are validated here only as well-formed
UUIDs. Existence checks against real rows (`stores`, `users`, and — for
`RECORD_REF` — other pages' `records`) need a database session, which this
module deliberately doesn't take; `app/services/record_service.py` runs
those checks itself for `STORE_REF`/`USER_REF` right after this model
validates shape. `RECORD_REF` existence/target-page checking is P4's
`reference_service.py` (see the plan's Context section for why).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model

from app.core.money import MoneyError, parse_money
from app.models.page_column import ColumnType, PageColumn

#: Columns with no client-writable representation in P3 — see module docstring.
_EXCLUDED_FROM_INPUT = frozenset({ColumnType.FORMULA, ColumnType.ATTACHMENT})


def _parse_decimal(value: Any) -> Decimal:
    """Like `app/core/money.py.parse_money`, but without money's fixed
    NUMERIC(14,2) range clamp — `NUMBER`/`PERCENT` columns set their own
    min/max via `config`."""
    if isinstance(value, bool):
        raise ValueError("bool is not a number")
    if isinstance(value, float):
        raise ValueError("float is not accepted; pass a string such as '42.5'")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty string is not a number")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a valid number") from exc
    else:
        raise ValueError(f"cannot parse {type(value).__name__} as a number")
    if not parsed.is_finite():
        raise ValueError("must be finite (not NaN or Infinity)")
    return parsed


def _currency_validator(config: dict[str, Any]) -> Any:
    allow_negative = bool(config.get("allow_negative", False))

    def _validate(value: Any) -> Decimal:
        try:
            parsed = parse_money(value)
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
        if not allow_negative and parsed < 0:
            raise ValueError("must not be negative")
        return parsed

    return Annotated[Decimal, BeforeValidator(_validate)]


def _number_validator(config: dict[str, Any], *, default_min: Decimal | None = None,
                       default_max: Decimal | None = None) -> Any:
    minimum = config.get("min", default_min)
    maximum = config.get("max", default_max)

    def _validate(value: Any) -> Decimal:
        parsed = _parse_decimal(value)
        if minimum is not None and parsed < Decimal(str(minimum)):
            raise ValueError(f"must be >= {minimum}")
        if maximum is not None and parsed > Decimal(str(maximum)):
            raise ValueError(f"must be <= {maximum}")
        return parsed

    return Annotated[Decimal, BeforeValidator(_validate)]


def _select_type(config: dict[str, Any], *, multi: bool) -> Any:
    options = config.get("options") or []
    string_options = tuple(str(o) for o in options)
    if not string_options:
        # Misconfigured column (no options) — schema_service should reject
        # this at column-creation time; fall back to plain str defensively
        # rather than building an empty, unsatisfiable Literal.
        base: Any = str
    else:
        base = _literal_from(string_options)
    return list[base] if multi else base


def _literal_from(options: tuple[str, ...]) -> Any:
    from typing import Literal

    return Literal[options]


def _field_type(column: PageColumn) -> Any:
    config = column.config or {}
    match column.data_type:
        case ColumnType.TEXT:
            return Annotated[str, Field(max_length=500)]
        case ColumnType.LONG_TEXT:
            return Annotated[str, Field(max_length=10_000)]
        case ColumnType.NUMBER:
            return _number_validator(config)
        case ColumnType.CURRENCY:
            return _currency_validator(config)
        case ColumnType.PERCENT:
            return _number_validator(config, default_min=Decimal(0), default_max=Decimal(100))
        case ColumnType.DATE:
            return date
        case ColumnType.DATETIME:
            return datetime
        case ColumnType.BOOLEAN:
            return bool
        case ColumnType.SELECT:
            return _select_type(config, multi=False)
        case ColumnType.MULTI_SELECT:
            return _select_type(config, multi=True)
        case ColumnType.RECORD_REF | ColumnType.STORE_REF | ColumnType.USER_REF:
            return uuid.UUID
        case _:  # pragma: no cover - FORMULA/ATTACHMENT excluded earlier
            raise AssertionError(f"{column.data_type} has no input field type")


def build_record_model(
    columns: Sequence[PageColumn],
    *,
    partial: bool = False,
    model_name: str = "RecordData",
    readonly_extra: frozenset[str] = frozenset(),
) -> type[BaseModel]:
    """Build a Pydantic model for one page's writable columns.

    `partial=True` builds the PATCH variant: every field becomes optional
    with no default forced, regardless of `is_required` — a PATCH only
    validates and changes the keys it actually receives.

    `readonly_extra` excludes columns from this *write* model the same way
    `FORMULA`/`ATTACHMENT` are excluded — by key rather than by type, since
    these are ordinary column types (e.g. `NUMBER`) that happen to be
    DB-computed for one particular page (a system page's generated column,
    `app/repositories/records.py`'s `GENERATED_COLUMNS`). Unlike
    `FORMULA`/`ATTACHMENT`, this only affects the write side — reads go
    through the dispatch layer directly, not this model.
    """
    fields: dict[str, Any] = {}
    for column in columns:
        if (
            column.is_archived
            or column.data_type in _EXCLUDED_FROM_INPUT
            or column.key in readonly_extra
        ):
            continue

        field_type = _field_type(column)
        config = column.config or {}

        if partial:
            fields[column.key] = (field_type | None, Field(default=None))
            continue

        if column.is_required:
            fields[column.key] = (field_type, Field(...))
        else:
            default = config.get("default")
            fields[column.key] = (field_type | None, Field(default=default))

    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
