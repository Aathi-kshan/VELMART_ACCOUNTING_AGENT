"""Safe expression parser (plan section 11.1, P4 §1) — the grammar shared by
FORMULA columns and `page_validations` rules.

**Design: default-deny, not default-allow-with-a-blocklist.** `_ALLOWED_NODES`
is the only thing this module trusts; any AST node type not in that set is
rejected the moment it's seen, so a dangerous node type nobody thought to
blocklist is structurally impossible rather than a future bug waiting to
happen. `ast.parse(expression, mode="eval")` already rules out statements
(assignment, `def`, `import`, loops) — those aren't legal in an expression —
so this module only has to reason about what *can* appear in one.

No `eval`/`exec` anywhere, ever (plan's own working agreement) — this parses
into an `ast.Expression` tree that `evaluator.py`/`sql_compiler.py` walk by
hand; the tree is never hands off to Python's own evaluator.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.errors import ExpressionSecurityError
from app.core.expressions.functions import FORMULA_FUNCTIONS

if TYPE_CHECKING:
    from app.models.page_column import PageColumn

#: `page_column.config` key holding a FORMULA column's expression source.
EXPRESSION_CONFIG_KEY = "expression"

#: Past this many characters, reject before even calling `ast.parse` — a
#: cheap guard against a pathologically large expression string.
MAX_EXPRESSION_LENGTH = 500

#: Past this much AST nesting, reject after parsing — same reasoning, aimed
#: at deeply-nested trees rather than long source text.
MAX_EXPRESSION_DEPTH = 20

#: `Expression` is the root `ast.parse(mode="eval")` always produces.
#: `IfExp` is how "if/else" exists in an expression grammar at all — Python
#: has no statement-if in eval mode, so the ternary `a if cond else b` is
#: the only, and intended, fit for the locked spec's "if/else" allowance.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Load,
    # Operator/comparator marker nodes — not "expressions" themselves, but
    # required children of BinOp/UnaryOp/BoolOp/Compare, so they must be
    # allowed too. Individually restricted below, not just by presence here.
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

#: Constant leaf types allowed (`ast.Constant.value`'s Python type) — numbers,
#: text, and booleans. `None` is deliberately excluded: a formula/validation
#: has no legitimate use for a literal null, and allowing it would just
#: invite `coalesce(x, None)`-style confusion when `coalesce()` already
#: exists for that.
_ALLOWED_CONSTANT_TYPES: tuple[type, ...] = (int, float, str, bool)


@dataclass(frozen=True)
class ParsedExpression:
    source: str
    tree: ast.Expression
    #: Column keys this expression reads — used both for the formula
    #: dependency graph (cycle detection) and for building the operand dict
    #: an evaluator/compiler needs.
    dependencies: frozenset[str]


def _depth(node: ast.AST, current: int = 0) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return current
    return max(_depth(child, current + 1) for child in children)


def parse_expression(expression: str, available_names: frozenset[str]) -> ParsedExpression:
    """Parse and validate a formula or `page_validations` expression.

    `available_names` is every operand this expression may legally
    reference — the page's own column keys (FORMULA columns included, so
    one formula can reference another; `formula_service.py` is what rejects
    a *cycle* of such references, not this function). Raises
    `ExpressionSecurityError` (422, `EXPRESSION_REJECTED`) with an
    Owner-facing message identifying exactly what was rejected — never a
    raw AST dump.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionSecurityError(
            f"Expression is too long (over {MAX_EXPRESSION_LENGTH} characters)."
        )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionSecurityError(f"Could not parse expression: {exc.msg}") from exc

    if _depth(tree) > MAX_EXPRESSION_DEPTH:
        raise ExpressionSecurityError("Expression is nested too deeply.")

    dependencies: set[str] = set()
    _validate_node(tree.body, available_names, dependencies, in_call_position=False)

    return ParsedExpression(source=expression, tree=tree, dependencies=frozenset(dependencies))


def _validate_node(
    node: ast.AST,
    available_names: frozenset[str],
    dependencies: set[str],
    *,
    in_call_position: bool,
) -> None:
    if not isinstance(node, _ALLOWED_NODES):
        raise ExpressionSecurityError(
            f"'{type(node).__name__}' is not allowed in an expression."
        )

    allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div)
    if isinstance(node, ast.BinOp) and not isinstance(node.op, allowed_binops):
        raise ExpressionSecurityError(f"'{type(node.op).__name__}' is not an allowed operator.")

    if isinstance(node, ast.Compare):
        for op in node.ops:
            if not isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                raise ExpressionSecurityError(
                    f"'{type(op).__name__}' is not an allowed comparison."
                )

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            pass  # bool is an int subclass; explicitly fine either way
        elif not isinstance(node.value, _ALLOWED_CONSTANT_TYPES):
            raise ExpressionSecurityError(
                f"'{node.value!r}' is not an allowed literal value."
            )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionSecurityError("Only calling a plain function name is allowed.")
        if node.func.id not in FORMULA_FUNCTIONS:
            raise ExpressionSecurityError(f"'{node.func.id}' is not a known function.")
        if node.keywords:
            raise ExpressionSecurityError("Keyword arguments are not allowed.")
        _validate_node(node.func, available_names, dependencies, in_call_position=True)
        for arg in node.args:
            _validate_node(arg, available_names, dependencies, in_call_position=False)
        return

    if isinstance(node, ast.Name):
        if in_call_position:
            if node.id not in FORMULA_FUNCTIONS:
                raise ExpressionSecurityError(f"'{node.id}' is not a known function.")
            return
        if node.id not in available_names:
            raise ExpressionSecurityError(f"'{node.id}' is not a column on this page.")
        dependencies.add(node.id)
        return

    for child in ast.iter_child_nodes(node):
        _validate_node(child, available_names, dependencies, in_call_position=False)


def get_column_expression(column: PageColumn) -> str:
    """A FORMULA column's expression source lives in its own `config`
    (`page_column.config[EXPRESSION_CONFIG_KEY]`) — this is the one place
    that reads it, so `formula_service.py` (the row-bounded Python
    evaluator) and `sql_compiler.py`/`app/repositories/records.py` (the
    aggregate/filter/sort SQL-compiled path) never drift on where it's
    stored."""
    expression = column.config.get(EXPRESSION_CONFIG_KEY)
    if not isinstance(expression, str) or not expression.strip():
        raise ExpressionSecurityError(f"{column.name!r} has no formula expression configured.")
    return expression


def parse_column_formula(column: PageColumn, all_columns: list[PageColumn]) -> ParsedExpression:
    """Parses one FORMULA column's expression against every *other* column
    key on the page (a formula may reference a non-formula column, or
    another formula column — `formula_service.check_for_cycles` is what
    rejects the latter when it loops back on itself, not this function)."""
    available = frozenset(c.key for c in all_columns if c.key != column.key)
    return parse_expression(get_column_expression(column), available)
