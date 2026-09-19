"""The Python evaluator and the SQL compiler must agree.

One grammar, two backends: `app/core/expressions/evaluator.py` computes a
FORMULA column's value when a record is read, and
`app/core/expressions/sql_compiler.py` compiles the same expression into SQL
so filtering, sorting and aggregating can happen in Postgres. If they
disagree, the number a user sees on a record differs from the number in that
page's total, and neither is obviously the wrong one.

Before this file the only cross-backend test was
`test_formula_engine.py::test_formula_value_matches_between_get_and_aggregate`,
which used a single addition on clean non-null data — the one case least
likely to diverge. Everything that actually differed went unnoticed:

* a `float` literal (`amount * 0.075`) bound as `double precision` in SQL
  while Python used `Decimal`, putting floating-point arithmetic on a money
  path and into the `SUM()` it fed;
* `days_between(a, b) / 2` was integer division in SQL (`2`) and true
  division in Python (`2.5`);
* `least()`/`greatest()` skip NULL arguments in Postgres, while Python
  propagates NULL, so `max(a, b)` with `b` unset disagreed;
* wrong arity crashed each backend differently, as a 500 rather than a 422.

The harness is deliberately simple: one record, one formula column. A `sum`
aggregate over a single row is that row's own formula value, so the two
backends can be compared directly on identical input.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

_OCCURRED = "2026-09-07T10:00:00+05:30"


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _page_with_formula(
    client: AsyncClient, headers: dict[str, str], expression: str
) -> str:
    """A page carrying two money columns, two dates, and `result` — the
    formula under test. Only `amount` is required, so a test can leave
    `other` unset and exercise NULL handling."""
    resp = await client.post(
        "/pages",
        json={
            "name": f"Parity {uuid.uuid4().hex[:6]}",
            "columns": [
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                {"name": "Other", "data_type": "CURRENCY"},
                {"name": "Start", "data_type": "DATE"},
                {"name": "End", "data_type": "DATE"},
                {
                    "name": "Result",
                    "data_type": "FORMULA",
                    "config": {"expression": expression},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _evaluate_both_ways(
    client: AsyncClient, headers: dict[str, str], expression: str, data: dict[str, str]
) -> tuple[str | None, str | None]:
    """Returns `(python_value, sql_value)` for one record.

    The first comes from `GET /records/{id}`, which applies formulas through
    the Python evaluator. The second comes from a `sum` aggregate over that
    single row, which Postgres computes from the compiled expression.
    """
    page_id = await _page_with_formula(client, headers, expression)

    created = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": _OCCURRED, "data": data},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    python_value = created.json()["data"]["result"]

    agg = await client.post(
        f"/pages/{page_id}/aggregate",
        json={"metric": "sum", "column": "result"},
        headers=headers,
    )
    assert agg.status_code == 200, agg.text
    return python_value, agg.json()["value"]


class TestNumericParity:
    """Expressions whose exact value both backends must produce."""

    @pytest.mark.parametrize(
        ("expression", "data", "expected"),
        [
            # A float literal on a money path — the case that made the whole
            # expression float8 in SQL.
            ("amount * 0.075", {"amount": "1000.00"}, Decimal("75")),
            ("amount * 0.1", {"amount": "10.00"}, Decimal("1")),
            # 0.07 has no exact binary representation, so a float would drift
            # here where Decimal and NUMERIC do not.
            ("amount * 0.07", {"amount": "100.00"}, Decimal("7")),
            ("amount + 0.01", {"amount": "0.02"}, Decimal("0.03")),
            # Integer literals stay integers (Postgres numeric op integer is
            # exact, and round() needs a real integer).
            ("amount * 3", {"amount": "1.15"}, Decimal("3.45")),
            ("round(amount * 0.075, 2)", {"amount": "999.99"}, Decimal("75.00")),
            ("abs(0 - amount)", {"amount": "42.50"}, Decimal("42.50")),
            ("sum(amount, amount)", {"amount": "1.11"}, Decimal("2.22")),
        ],
    )
    async def test_both_backends_agree(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        expression: str,
        data: dict[str, str],
        expected: Decimal,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, expression, data
        )
        assert python_value is not None and sql_value is not None
        assert Decimal(python_value) == expected, f"Python evaluator: {python_value}"
        assert Decimal(sql_value) == expected, f"SQL compiler: {sql_value}"

    async def test_division_is_true_division_not_integer_division(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """`days_between` is a day count — an `integer` in Postgres and a
        `Decimal` in Python. Dividing it must not silently truncate on one
        backend only."""
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client,
            headers,
            "days_between(start, end) / 2",
            {"amount": "1.00", "start": "2026-09-01", "end": "2026-09-08"},
        )
        assert python_value is not None and sql_value is not None
        # 7 days / 2 — 3.5, never 3.
        assert Decimal(python_value) == Decimal("3.5"), f"Python: {python_value}"
        assert Decimal(sql_value) == Decimal("3.5"), f"SQL: {sql_value}"

    async def test_non_terminating_division_agrees_once_rounded(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """`10/3` cannot be represented exactly in either backend, and
        Python's `Decimal` and Postgres `NUMERIC` carry different default
        precision, so the raw quotients legitimately differ in their trailing
        digits. What must agree is the rounded value — which is what a money
        column ever displays or totals."""
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, "round(amount / 3, 2)", {"amount": "10.00"}
        )
        assert python_value is not None and sql_value is not None
        assert Decimal(python_value) == Decimal("3.33"), f"Python: {python_value}"
        assert Decimal(sql_value) == Decimal("3.33"), f"SQL: {sql_value}"


class TestNullParity:
    """A missing operand must mean the same thing on both backends."""

    @pytest.mark.parametrize("expression", ["max(amount, other)", "min(amount, other)"])
    async def test_min_and_max_propagate_a_missing_operand(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, expression: str
    ) -> None:
        """Postgres `least()`/`greatest()` ignore NULLs and would return
        `amount`; the Python evaluator propagates NULL. Propagating is the
        rule here — a total that silently treats "not entered yet" as
        "not a candidate" is the kind of wrong number nobody notices."""
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, expression, {"amount": "500.00"}
        )
        assert python_value is None, f"Python evaluator returned {python_value!r}"
        # Summing a single NULL row yields no total at all.
        assert sql_value is None or Decimal(sql_value) == 0, f"SQL compiler: {sql_value!r}"

    async def test_min_and_max_still_compare_when_both_operands_are_present(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The NULL guard must not break the ordinary case."""
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, "max(amount, other)", {"amount": "10.00", "other": "40.00"}
        )
        assert python_value is not None and sql_value is not None
        assert Decimal(python_value) == Decimal("40.00")
        assert Decimal(sql_value) == Decimal("40.00")

    async def test_coalesce_is_the_one_function_that_absorbs_nulls(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, "coalesce(other, amount)", {"amount": "7.00"}
        )
        assert python_value is not None and sql_value is not None
        assert Decimal(python_value) == Decimal("7.00")
        assert Decimal(sql_value) == Decimal("7.00")

    async def test_safe_div_returns_its_default_on_both_backends(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        python_value, sql_value = await _evaluate_both_ways(
            client, headers, "safe_div(amount, 0, 99)", {"amount": "10.00"}
        )
        assert python_value is not None and sql_value is not None
        assert Decimal(python_value) == Decimal("99")
        assert Decimal(sql_value) == Decimal("99")


class TestCreatePageValidatesFormulas:
    """`POST /pages` used to accept any FORMULA expression at all.

    Only `POST /pages/{id}/columns` and `PATCH /columns/{id}` ran the
    whitelist parser, so an expression in the *initial* page payload was
    never checked. The column then failed silently on read —
    `formula_service.prepare` catches the parse error and degrades the page
    to "every formula is blank" — or, for a bad arity, raised from inside the
    SQL compiler as a 500 the first time anyone filtered or totalled it.
    """

    @pytest.mark.parametrize(
        ("expression", "reason"),
        [
            ("amount + nonexistent", "names a column that does not exist"),
            ("amount.__class__", "attribute access"),
            ("__import__('os')", "an unknown function"),
            ("[amount]", "a disallowed node type"),
        ],
    )
    async def test_an_invalid_expression_is_rejected_at_create(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        expression: str,
        reason: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": f"Invalid {uuid.uuid4().hex[:6]}",
                "columns": [
                    {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                    {
                        "name": "Result",
                        "data_type": "FORMULA",
                        "config": {"expression": expression},
                    },
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"accepted {reason}: {resp.text}"

    async def test_a_cycle_inside_the_initial_payload_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Two formulas in one payload can reference each other."""
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": f"Cycle {uuid.uuid4().hex[:6]}",
                "columns": [
                    {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                    {"name": "A", "data_type": "FORMULA", "config": {"expression": "b"}},
                    {"name": "B", "data_type": "FORMULA", "config": {"expression": "a"}},
                ],
            },
            headers=headers,
        )
        assert resp.status_code in (409, 422), resp.text

    async def test_a_valid_formula_is_still_accepted_at_create(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The guard must not block the ordinary case — a formula referencing
        columns defined alongside it in the same payload."""
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": f"Valid {uuid.uuid4().hex[:6]}",
                "columns": [
                    {"name": "Basic", "data_type": "CURRENCY", "is_required": True},
                    {"name": "Bonus", "data_type": "CURRENCY", "is_required": True},
                    {
                        "name": "Net",
                        "data_type": "FORMULA",
                        "config": {"expression": "basic + bonus"},
                    },
                    {
                        "name": "Net After Tax",
                        "data_type": "FORMULA",
                        "config": {"expression": "net * 0.85"},
                    },
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text


class TestArityIsRejectedAtSaveTime:
    """A call with the wrong number of arguments must be a 422 when the
    column is defined, not a 500 from inside a query later on."""

    @pytest.mark.parametrize(
        "expression",
        [
            "sum()",
            "min()",
            "max()",
            "coalesce()",
            "abs()",
            "abs(amount, amount)",
            "days_between(start)",
            "days_between(start, end, start)",
            "safe_div(amount)",
            "today(amount)",
            "round()",
            "round(amount, 2, 3)",
        ],
    )
    async def test_wrong_arity_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, expression: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": f"Arity {uuid.uuid4().hex[:6]}",
                "columns": [
                    {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                    {"name": "Start", "data_type": "DATE"},
                    {"name": "End", "data_type": "DATE"},
                    {
                        "name": "Result",
                        "data_type": "FORMULA",
                        "config": {"expression": expression},
                    },
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"{expression!r} was accepted: {resp.text}"
        assert resp.json()["code"] == "EXPRESSION_REJECTED"

    @pytest.mark.parametrize(
        "expression",
        [
            "sum(amount)",
            "sum(amount, amount, amount)",
            "round(amount)",
            "round(amount, 2)",
            "safe_div(amount, amount)",
            "safe_div(amount, amount, 0)",
            "days_between(start, end)",
            "today()",
            "coalesce(amount)",
        ],
    )
    async def test_correct_arity_is_still_accepted(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, expression: str
    ) -> None:
        """The guard must not reject the variadic and optional-argument forms
        the grammar genuinely supports."""
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": f"Arity OK {uuid.uuid4().hex[:6]}",
                "columns": [
                    {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                    {"name": "Start", "data_type": "DATE"},
                    {"name": "End", "data_type": "DATE"},
                    {
                        "name": "Result",
                        "data_type": "FORMULA",
                        "config": {"expression": expression},
                    },
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201, f"{expression!r} was rejected: {resp.text}"
