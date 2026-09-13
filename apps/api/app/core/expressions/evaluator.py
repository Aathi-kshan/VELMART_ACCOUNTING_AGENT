"""The `Decimal` evaluator (plan section 11.1, P4 §3) — walks a
`ParsedExpression` tree the parser already proved is safe, computing its
result against a dict of the record's other column values (already
Python-typed — `Decimal`, `date`, `str`, `bool` — the same shape
`build_record_model(...).model_dump()` produces).

**A missing operand propagates as `None`, it is never silently treated as
zero.** An accounting formula that quietly substituted 0 for a blank input
would hide exactly the kind of data-entry gap it should surface — a
formula showing blank tells the Owner "this can't be computed yet, go
check," which is the honest answer.

**Read-path robustness, an explicit design decision:** a formula that fails
at evaluation time (raw `/` by zero, an operator applied to incompatible
types) must not fail the *entire* record read — one bad formula on one
record must not 500 a list of fifty. `evaluate()` raises
`FormulaEvaluationError`; the caller (`formula_service.py`) catches it
*per column* and sets that column's value to `None` in the response,
matching how a genuinely-empty FORMULA already renders
(`formula_field_renderer.dart` already treats `null` as "computed
automatically").
"""

from __future__ import annotations

import ast
from decimal import Decimal, DecimalException
from typing import Any

from app.core.expressions.functions import FORMULA_FUNCTIONS
from app.core.expressions.parser import ParsedExpression


class FormulaEvaluationError(Exception):
    """A parsed, security-validated expression failed at evaluation time —
    e.g. a raw `/` by zero, or an operator applied to incompatible operand
    types. Never raised for anything the parser should already have
    caught; this is purely runtime data conditions."""


def evaluate(parsed: ParsedExpression, operands: dict[str, Any]) -> Any:
    try:
        return _eval_node(parsed.tree.body, operands)
    except FormulaEvaluationError:
        raise
    except (DecimalException, TypeError, ValueError, ZeroDivisionError, AttributeError) as exc:
        raise FormulaEvaluationError(str(exc)) from exc


def _coerce_constant(value: Any) -> Any:
    """A literal number in the expression's own source text (`0.5`, `100`)
    becomes a `Decimal` so it participates in `Decimal` arithmetic — Python's
    `Decimal` refuses to mix with a raw `float` at all (`TypeError`) and
    silently upcasting an `int` operand is harmless. `str(value)` round-trips
    an ordinary decimal literal cleanly; this is a literal token the Owner
    typed, not an arbitrary computed float, so there's no precision already
    lost to recover from."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    return value


def _eval_node(node: ast.AST, operands: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return _coerce_constant(node.value)

    if isinstance(node, ast.Name):
        if node.id not in operands:
            raise FormulaEvaluationError(f"'{node.id}' has no value for this record.")
        return operands[node.id]

    if isinstance(node, ast.BinOp):
        return _eval_binop(node, operands)

    if isinstance(node, ast.UnaryOp):
        return _eval_unaryop(node, operands)

    if isinstance(node, ast.BoolOp):
        values = [_eval_node(value, operands) for value in node.values]
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in values:
                result = result and value
            return result
        result = False
        for value in values:
            result = result or value
        return result

    if isinstance(node, ast.Compare):
        return _eval_compare(node, operands)

    if isinstance(node, ast.IfExp):
        test = _eval_node(node.test, operands)
        return _eval_node(node.body, operands) if test else _eval_node(node.orelse, operands)

    if isinstance(node, ast.Call):
        return _eval_call(node, operands)

    raise FormulaEvaluationError(f"Cannot evaluate node type {type(node).__name__}.")


def _eval_binop(node: ast.BinOp, operands: dict[str, Any]) -> Any:
    left = _eval_node(node.left, operands)
    right = _eval_node(node.right, operands)
    if left is None or right is None:
        return None
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        if right == 0:
            raise FormulaEvaluationError("Division by zero — use safe_div if this is expected.")
        return left / right
    # pragma: no cover - the parser already restricts BinOp to these four
    raise FormulaEvaluationError(f"Unsupported operator {type(node.op).__name__}.")


def _eval_unaryop(node: ast.UnaryOp, operands: dict[str, Any]) -> Any:
    operand = _eval_node(node.operand, operands)
    if operand is None:
        return None
    if isinstance(node.op, ast.UAdd):
        return +operand
    if isinstance(node.op, ast.USub):
        return -operand
    if isinstance(node.op, ast.Not):
        return not operand
    raise FormulaEvaluationError(  # pragma: no cover - parser already restricts this
        f"Unsupported unary operator {type(node.op).__name__}."
    )


def _eval_compare(node: ast.Compare, operands: dict[str, Any]) -> Any:
    left = _eval_node(node.left, operands)
    for op, comparator in zip(node.ops, node.comparators, strict=True):
        right = _eval_node(comparator, operands)
        if left is None or right is None:
            return None
        if not _compare_one(op, left, right):
            return False
        left = right
    return True


def _compare_one(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return bool(left == right)
    if isinstance(op, ast.NotEq):
        return bool(left != right)
    if isinstance(op, ast.Lt):
        return bool(left < right)
    if isinstance(op, ast.LtE):
        return bool(left <= right)
    if isinstance(op, ast.Gt):
        return bool(left > right)
    if isinstance(op, ast.GtE):
        return bool(left >= right)
    raise FormulaEvaluationError(f"Unsupported comparison {type(op).__name__}.")  # pragma: no cover


def _eval_call(node: ast.Call, operands: dict[str, Any]) -> Any:
    assert isinstance(node.func, ast.Name)  # guaranteed by the parser
    name = node.func.id
    func = FORMULA_FUNCTIONS[name]
    args = [_eval_node(arg, operands) for arg in node.args]
    # `coalesce`'s entire job is handling `None` arguments — every other
    # function propagates `None` rather than guessing what a missing
    # operand should mean to it.
    if name != "coalesce" and any(arg is None for arg in args):
        return None
    return func(*args)
