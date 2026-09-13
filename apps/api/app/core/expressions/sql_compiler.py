"""Compiles the *same* whitelist expression grammar `evaluator.py` interprets
into a SQLAlchemy expression tree instead (plan section 11.1, P4 §4) — a
second backend for one grammar, not a second grammar.

Why this exists at all: FORMULA columns are never stored, so summing one
across a filtered set can't mean "fetch every matching row into Python and
add them up" — `docs/API.md` §5 already states aggregation runs "in
Postgres, in Decimal, never in Python", a rule written before formulas
needed to participate in it. `app/repositories/records.py`'s
`resolve_column` is the single place this gets wired in: when the resolved
column is a FORMULA, it returns a compiled expression instead of a plain
column reference, so `query_service.py`'s filter, sort, *and* aggregate
paths all gain formula support through the one function they already call,
with no separate plumbing per caller.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from sqlalchemy import Date, case, cast, func
from sqlalchemy.sql import ColumnElement

from app.core.expressions.parser import ParsedExpression

ResolveColumn = Callable[[str], ColumnElement[Any]]


def compile_formula_to_sql(parsed: ParsedExpression, resolve: ResolveColumn) -> ColumnElement[Any]:
    """`resolve` maps an operand column key to its own SQL expression —
    ordinarily a plain column, but for a formula that itself references
    another formula, the caller's own `resolve_column` recurses back into
    this function for that dependency. Cycle-safety is already guaranteed
    at column save time (`formula_service.check_for_cycles`), so this
    recursion is guaranteed to terminate."""
    return _compile_node(parsed.tree.body, resolve)


def _compile_node(node: ast.AST, resolve: ResolveColumn) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return resolve(node.id)

    if isinstance(node, ast.BinOp):
        left = _compile_node(node.left, resolve)
        right = _compile_node(node.right, resolve)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            # Mirrors `safe_div`'s own zero-guard rather than letting
            # Postgres raise `division_by_zero` mid-aggregate.
            return case((right == 0, None), else_=left / right)
        raise AssertionError(type(node.op))  # pragma: no cover - parser restricts this

    if isinstance(node, ast.UnaryOp):
        operand = _compile_node(node.operand, resolve)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return ~operand
        raise AssertionError(type(node.op))  # pragma: no cover - parser restricts this

    if isinstance(node, ast.BoolOp):
        values = [_compile_node(value, resolve) for value in node.values]
        combined = values[0]
        for value in values[1:]:
            combined = (combined & value) if isinstance(node.op, ast.And) else (combined | value)
        return combined

    if isinstance(node, ast.Compare):
        left = _compile_node(node.left, resolve)
        clauses = []
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _compile_node(comparator, resolve)
            clauses.append(_compile_compare(op, left, right))
            left = right
        result = clauses[0]
        for clause in clauses[1:]:
            result = result & clause
        return result

    if isinstance(node, ast.IfExp):
        test = _compile_node(node.test, resolve)
        body = _compile_node(node.body, resolve)
        orelse = _compile_node(node.orelse, resolve)
        return case((test, body), else_=orelse)

    if isinstance(node, ast.Call):
        return _compile_call(node, resolve)

    raise AssertionError(type(node))  # pragma: no cover - parser restricts this


def _compile_compare(op: ast.cmpop, left: Any, right: Any) -> Any:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    raise AssertionError(op)  # pragma: no cover - parser restricts this


def _compile_call(node: ast.Call, resolve: ResolveColumn) -> Any:
    assert isinstance(node.func, ast.Name)  # guaranteed by the parser
    name = node.func.id
    args = [_compile_node(arg, resolve) for arg in node.args]

    if name == "sum":
        total = args[0]
        for arg in args[1:]:
            total = total + arg
        return total
    if name == "min":
        return func.least(*args) if len(args) > 1 else args[0]
    if name == "max":
        return func.greatest(*args) if len(args) > 1 else args[0]
    if name == "round":
        return func.round(*args)
    if name == "abs":
        return func.abs(args[0])
    if name == "safe_div":
        numerator, denominator = args[0], args[1]
        default = args[2] if len(args) > 2 else 0
        return case((denominator == 0, default), else_=numerator / denominator)
    if name == "days_between":
        # Cast both sides to DATE first (dropping any time-of-day component,
        # matching `functions.fn_days_between`'s own `_as_date` normalisation)
        # so this is always `date - date`, which Postgres returns as a plain
        # integer day count directly — never an INTERVAL needing `date_part`.
        return cast(args[1], Date) - cast(args[0], Date)
    if name == "today":
        # Mirrors `functions.fn_today`'s company-local "today", not a bare
        # UTC `CURRENT_DATE` — same midnight-boundary reasoning throughout.
        return cast(func.timezone("Asia/Colombo", func.now()), Date)
    if name == "coalesce":
        return func.coalesce(*args)
    raise AssertionError(name)  # pragma: no cover - parser restricts this
