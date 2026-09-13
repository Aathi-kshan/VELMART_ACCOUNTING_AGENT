"""FORMULA columns (plan section 11.1, P4 §4) — cycle rejection at save
time via a dependency graph over column keys, and computed on read (never
stored, never drifting from its inputs).

Aggregation's own formula support (compiling the same whitelist grammar to
SQL instead of interpreting it) lives in `app/core/expressions/sql_compiler.py`
and is wired in through `app/repositories/records.py`'s `resolve_column` —
this module is the row-bounded read path and the save-time cycle check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.errors import ExpressionSecurityError, FormulaCycleError
from app.core.expressions.evaluator import FormulaEvaluationError, evaluate
from app.core.expressions.parser import get_column_expression, parse_column_formula
from app.models.page_column import ColumnType, PageColumn
from app.schemas.dynamic import build_record_model

#: Re-exported for callers that only need the raw expression string (e.g.
#: the Flutter validation editor's preview) — the parsing/graph logic below
#: is this module's own addition on top of `app.core.expressions.parser`.
get_expression = get_column_expression
parse_formula = parse_column_formula


def build_dependency_graph(columns: list[PageColumn]) -> dict[str, frozenset[str]]:
    """`formula column key -> the *other formula columns'* keys it
    references`, directly. A formula's non-formula dependencies are leaves,
    not graph nodes — a cycle can only occur formula-to-formula."""
    formula_keys = {c.key for c in columns if c.data_type is ColumnType.FORMULA}
    graph: dict[str, frozenset[str]] = {}
    for column in columns:
        if column.data_type is not ColumnType.FORMULA:
            continue
        parsed = parse_formula(column, columns)
        graph[column.key] = frozenset(parsed.dependencies & formula_keys)
    return graph


def check_for_cycles(graph: dict[str, frozenset[str]]) -> None:
    """Hand-rolled DFS cycle detection (three-colour visiting/visited
    marking) — a page has at most a couple of dozen columns, nowhere near
    enough to justify a graph library as a dependency for this."""
    WHITE, GRAY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)
    path: list[str] = []

    def visit(node: str) -> None:
        colour[node] = GRAY
        path.append(node)
        for neighbour in graph.get(node, frozenset()):
            if colour.get(neighbour, WHITE) == GRAY:
                cycle = " -> ".join((*path[path.index(neighbour) :], neighbour))
                raise FormulaCycleError(f"Formula columns form a cycle: {cycle}.")
            if colour.get(neighbour, WHITE) == WHITE:
                visit(neighbour)
        path.pop()
        colour[node] = BLACK

    for node in graph:
        if colour[node] == WHITE:
            visit(node)


def topological_order(graph: dict[str, frozenset[str]]) -> list[str]:
    """Assumes `check_for_cycles` already passed. A formula referencing
    another formula must see the *already-computed* value, never
    re-evaluate it or see it out of order."""
    order: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for neighbour in graph.get(node, frozenset()):
            visit(neighbour)
        order.append(node)

    for node in graph:
        visit(node)
    return order


def validate_formula_column(column: PageColumn, all_columns: list[PageColumn]) -> None:
    """Called from `schema_service.add_column`/`update_column` when saving a
    FORMULA column: parses the expression (rejecting anything the whitelist
    parser doesn't allow) and rebuilds the *whole page's* formula dependency
    graph, rejecting at save time if this column introduces a cycle. Fail
    at save, never at read — the same principle every other schema
    validation in this codebase already follows."""
    parse_formula(column, all_columns)  # raises ExpressionSecurityError if invalid
    graph = build_dependency_graph(all_columns)
    check_for_cycles(graph)


def _to_wire(value: Any) -> Any:
    """A formula result is a Python-typed value straight out of the
    evaluator (`Decimal`, `date`, `bool`, ...) — every *other* key already
    sitting in a `RecordHandle.data` dict is wire format (a money string,
    ISO date text — plan section 9.1), and this one must match or a raw
    `Decimal` would serialize as a bare JSON number, exactly what the
    "money is always a string" rule exists to prevent."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


@dataclass
class FormulaPlan:
    """Everything `apply_prepared` needs, built once per page/schema rather
    than once per row — `query_records` prepares a plan before its row
    loop and reuses it across every row on the page; `apply_formulas` below
    is the single-row convenience wrapper `record_service.py`'s
    create/get/update use, each handling exactly one record."""

    order: list[str]
    by_key: dict[str, PageColumn]
    #: `None` when the page has no FORMULA columns at all.
    operand_model: type[BaseModel] | None


def prepare(columns: list[PageColumn]) -> FormulaPlan:
    formula_columns = [c for c in columns if c.data_type is ColumnType.FORMULA]
    by_key = {c.key: c for c in formula_columns}
    if not formula_columns:
        return FormulaPlan(order=[], by_key={}, operand_model=None)

    non_formula_columns = [c for c in columns if c.data_type is not ColumnType.FORMULA]
    operand_model = build_record_model(non_formula_columns, partial=True)

    try:
        graph = build_dependency_graph(columns)
        order = topological_order(graph)
    except (ExpressionSecurityError, FormulaCycleError):
        # Save-time validation (`validate_formula_column`) should make this
        # unreachable — defensive only, so a corrupt/legacy config degrades
        # a read into "every formula is blank" rather than a crash.
        order = list(by_key)

    return FormulaPlan(order=order, by_key=by_key, operand_model=operand_model)


def _compute_typed(
    plan: FormulaPlan, columns: list[PageColumn], operands: dict[str, Any]
) -> dict[str, Any]:
    """`operands` is already Python-typed (`Decimal`, `date`, ...) and is
    mutated in place as each formula's result becomes available to the
    next — a formula referencing another formula must see its
    already-computed value, in topological order. Returns just the
    computed formula values, still Python-typed (never wire-converted) —
    `apply_prepared` wire-converts for a read response;
    `compute_typed_values` hands them straight to `validation_service.py`,
    which needs real types to evaluate a rule like `total > 0`."""
    values: dict[str, Any] = {}
    for key in plan.order:
        column = plan.by_key[key]
        try:
            parsed = parse_formula(column, columns)
            value = evaluate(parsed, operands)
        except (ExpressionSecurityError, FormulaEvaluationError):
            value = None
        operands[key] = value  # a dependent formula sees this one's computed value
        values[key] = value
    return values


def _typed_operands(
    plan: FormulaPlan, data: dict[str, Any]
) -> dict[str, Any] | None:
    """`data` may be wire format (a money string, ISO date text) or already
    Python-typed — `build_record_model`'s validators accept either, so this
    serves both `apply_prepared` (reading stored, wire-format data back) and
    `compute_typed_values` (record_service's own write-time, already-typed
    `validated` dict) without a second parsing path. Returns `None` if the
    page's schema narrowed since this data was produced and it no longer
    parses under the new types — every formula is then unknowable, not a
    crash."""
    assert plan.operand_model is not None
    raw_operands = {k: v for k, v in data.items() if k in plan.operand_model.model_fields}
    try:
        return dict(plan.operand_model(**raw_operands).model_dump())
    except ValidationError:
        return None


def apply_prepared(
    plan: FormulaPlan, columns: list[PageColumn], data: dict[str, Any]
) -> dict[str, Any]:
    """`data` is wire format (a money string, ISO date text) — the
    evaluator needs real Python-typed operands (`Decimal`, `date`, ...), the
    same shape `build_record_model` already knows how to parse incoming
    wire input into. Reusing it here means there is exactly one place in
    this codebase that parses a page's wire-format data, not a second,
    independently-maintained copy of that logic just for formulas."""
    if plan.operand_model is None:
        return data

    operands = _typed_operands(plan, data)
    if operands is None:
        result = dict(data)
        for key in plan.by_key:
            result[key] = None
        return result

    computed = _compute_typed(plan, columns, operands)
    result = dict(data)
    for key, value in computed.items():
        result[key] = _to_wire(value)
    return result


def compute_typed_values(
    plan: FormulaPlan, columns: list[PageColumn], data: dict[str, Any]
) -> dict[str, Any]:
    """Write-time counterpart to `apply_prepared`, for `validation_service.py`
    (P4 §6): `data` here is `record_service`'s own already-Python-typed
    `validated`/merged dict, never wire format, and the return value stays
    Python-typed too — merged straight into a `page_validations` rule's
    operand dict, never round-tripped through wire text first."""
    if plan.operand_model is None:
        return {}
    operands = _typed_operands(plan, data)
    if operands is None:
        return dict.fromkeys(plan.by_key, None)
    return _compute_typed(plan, columns, operands)


def apply_formulas(columns: list[PageColumn], data: dict[str, Any]) -> dict[str, Any]:
    """Single-row convenience wrapper — see `FormulaPlan`'s docstring for
    when to call `prepare()`/`apply_prepared()` directly instead."""
    return apply_prepared(prepare(columns), columns, data)
