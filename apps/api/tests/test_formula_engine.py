"""FORMULA columns — the safe expression parser, function library, Decimal
evaluator, dependency-graph cycle detection, and the SQL-compiled aggregate
path (plan section 11.1, P4 §1-4). See `test_record_validation.py` for the
"a formula is never accepted as input" boundary; this file is the engine
itself.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response

from app.core.errors import ExpressionSecurityError
from app.core.expressions.evaluator import FormulaEvaluationError, evaluate
from app.core.expressions.functions import (
    fn_abs,
    fn_coalesce,
    fn_days_between,
    fn_max,
    fn_min,
    fn_round,
    fn_safe_div,
    fn_sum,
)
from app.core.expressions.parser import parse_expression


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _create_page(
    client: AsyncClient, headers: dict[str, str], columns: list[dict]
) -> str:
    resp = await client.post(
        "/pages", json={"name": "Staff", "columns": columns}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _add_column(
    client: AsyncClient, headers: dict[str, str], page_id: str, column: dict
) -> Response:
    return await client.post(f"/pages/{page_id}/columns", json=column, headers=headers)


class TestFunctionLibrary:
    """Every function in the whitelist, against hand-computed results."""

    def test_sum(self) -> None:
        assert fn_sum(Decimal("1"), Decimal("2"), Decimal("3")) == Decimal("6")

    def test_min_max(self) -> None:
        args = (Decimal("3"), Decimal("1"), Decimal("2"))
        assert fn_min(*args) == Decimal("1")
        assert fn_max(*args) == Decimal("3")

    def test_round_half_up(self) -> None:
        # ROUND_HALF_UP, never banker's rounding: 2.5 -> 3, not 2.
        assert fn_round(Decimal("2.5"), 0) == Decimal("3")
        assert fn_round(Decimal("1.005"), 2) == Decimal("1.01")

    def test_abs(self) -> None:
        assert fn_abs(Decimal("-5.50")) == Decimal("5.50")

    def test_safe_div_by_zero_returns_default(self) -> None:
        assert fn_safe_div(Decimal("10"), Decimal("0")) == Decimal("0")
        assert fn_safe_div(Decimal("10"), Decimal("0"), Decimal("-1")) == Decimal("-1")
        assert fn_safe_div(Decimal("10"), Decimal("4")) == Decimal("2.5")

    def test_days_between(self) -> None:
        from datetime import date

        assert fn_days_between(date(2026, 9, 1), date(2026, 9, 11)) == Decimal(10)

    def test_coalesce_first_non_none(self) -> None:
        assert fn_coalesce(None, None, Decimal("5")) == Decimal("5")
        assert fn_coalesce(None, None) is None


class TestParserWhitelist:
    """Every banned construct is rejected individually — default-deny, not a
    blocklist that might miss one."""

    def _reject(self, expression: str) -> None:
        with pytest.raises(ExpressionSecurityError):
            parse_expression(expression, frozenset({"amount", "basic", "bonus"}))

    def test_attribute_access_rejected(self) -> None:
        self._reject("amount.__class__")

    def test_import_rejected(self) -> None:
        self._reject("__import__('os')")

    def test_comprehension_rejected(self) -> None:
        self._reject("[x for x in [1, 2]]")

    def test_lambda_rejected(self) -> None:
        self._reject("(lambda: amount)()")

    def test_call_to_unknown_function_rejected(self) -> None:
        self._reject("eval(amount)")

    def test_subscript_rejected(self) -> None:
        self._reject("amount[0]")

    def test_unknown_operator_rejected(self) -> None:
        self._reject("amount ** 2")

    def test_membership_comparison_rejected(self) -> None:
        self._reject("amount in [1, 2]")

    def test_unknown_column_name_rejected(self) -> None:
        self._reject("not_a_real_column")

    def test_expression_too_long_rejected(self) -> None:
        self._reject("amount + " + "1 + " * 200 + "1")

    def test_valid_expression_is_accepted(self) -> None:
        parsed = parse_expression(
            "round(safe_div(basic, bonus), 2)", frozenset({"basic", "bonus"})
        )
        assert parsed.dependencies == frozenset({"basic", "bonus"})


class TestEvaluatorRuntimeBehaviour:
    def test_missing_operand_propagates_as_none_not_zero(self) -> None:
        parsed = parse_expression("amount + bonus", frozenset({"amount", "bonus"}))
        result = evaluate(parsed, {"amount": Decimal("10"), "bonus": None})
        assert result is None

    def test_raw_division_by_zero_raises(self) -> None:
        parsed = parse_expression("amount / bonus", frozenset({"amount", "bonus"}))
        with pytest.raises(FormulaEvaluationError):
            evaluate(parsed, {"amount": Decimal("10"), "bonus": Decimal("0")})

    def test_safe_div_by_zero_does_not_raise(self) -> None:
        parsed = parse_expression("safe_div(amount, bonus)", frozenset({"amount", "bonus"}))
        assert evaluate(parsed, {"amount": Decimal("10"), "bonus": Decimal("0")}) == Decimal("0")


class TestFormulaColumnEndToEnd:
    """Formula columns via the real API — cycle rejection, dependent-formula
    ordering, and read/aggregate parity (docs/API.md §5's "aggregation runs
    in Postgres, in Decimal, never in Python", now including formulas)."""

    async def _staff_page(self, client: AsyncClient, headers: dict[str, str]) -> str:
        return await _create_page(
            client,
            headers,
            columns=[
                {"name": "Basic", "data_type": "CURRENCY", "is_required": True},
                {"name": "OT", "data_type": "CURRENCY", "is_required": True},
                {"name": "Bonus", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Net Salary",
                    "data_type": "FORMULA",
                    "config": {"expression": "basic + ot + bonus"},
                },
            ],
        )

    async def test_direct_cycle_rejected_at_save_time(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        # Build the page valid, then close the loop by editing one column —
        # the same shape as `test_transitive_cycle_rejected_at_save_time`.
        # This used to create the page with `basic + circular` already in
        # place, which only worked because `POST /pages` did not validate
        # FORMULA expressions at all: an expression naming a column that did
        # not exist was accepted, and the column silently read as blank
        # forever. `page_service.create_page` now validates them, so the
        # cycle has to be introduced through a path that still accepts it.
        page_id = await _create_page(
            client,
            headers,
            columns=[
                {"name": "Basic", "data_type": "CURRENCY", "is_required": True},
                {"name": "Total", "data_type": "FORMULA", "config": {"expression": "basic"}},
            ],
        )
        circular = await _add_column(
            client,
            headers,
            page_id,
            {"name": "Circular", "data_type": "FORMULA", "config": {"expression": "total"}},
        )
        assert circular.status_code == 201, circular.text

        # total -> circular -> total is a direct cycle.
        schema = await client.get(f"/pages/{page_id}/schema", headers=headers)
        total_column_id = next(c["id"] for c in schema.json()["columns"] if c["key"] == "total")
        resp = await client.patch(
            f"/columns/{total_column_id}",
            json={"config": {"expression": "circular"}},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "FORMULA_CYCLE"

    async def test_transitive_cycle_rejected_at_save_time(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(
            client,
            headers,
            columns=[
                {"name": "Basic", "data_type": "CURRENCY", "is_required": True},
                {"name": "A", "data_type": "FORMULA", "config": {"expression": "basic"}},
            ],
        )
        b_resp = await _add_column(
            client,
            headers,
            page_id,
            {"name": "B", "data_type": "FORMULA", "config": {"expression": "a"}},
        )
        assert b_resp.status_code == 201, b_resp.text

        # A -> A through B -> C -> A is a transitive cycle, not a direct one.
        c_resp = await _add_column(
            client,
            headers,
            page_id,
            {"name": "C", "data_type": "FORMULA", "config": {"expression": "b"}},
        )
        assert c_resp.status_code == 201, c_resp.text

        schema = await client.get(f"/pages/{page_id}/schema", headers=headers)
        a_column_id = next(
            c["id"] for c in schema.json()["columns"] if c["key"] == "a"
        )
        patch = await client.patch(
            f"/columns/{a_column_id}",
            json={"config": {"expression": "c"}},
            headers=headers,
        )
        assert patch.status_code == 409, patch.text
        assert patch.json()["code"] == "FORMULA_CYCLE"

    async def test_formula_referencing_another_formula_evaluates_in_order(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(
            client,
            headers,
            columns=[
                {"name": "Basic", "data_type": "CURRENCY", "is_required": True},
                {"name": "OT", "data_type": "CURRENCY", "is_required": True},
                {"name": "Gross", "data_type": "FORMULA", "config": {"expression": "basic + ot"}},
                {
                    "name": "Net",
                    "data_type": "FORMULA",
                    "config": {"expression": "gross - 10"},
                },
            ],
        )
        create = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"basic": "100.00", "ot": "20.00"},
            },
            headers=headers,
        )
        assert create.status_code == 201, create.text
        body = create.json()["data"]
        assert body["gross"] == "120.00"
        assert body["net"] == "110.00"

    async def test_runtime_division_by_zero_yields_null_not_500(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(
            client,
            headers,
            columns=[
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                {"name": "Divisor", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Ratio",
                    "data_type": "FORMULA",
                    "config": {"expression": "amount / divisor"},
                },
            ],
        )
        create = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "10.00", "divisor": "0.00"},
            },
            headers=headers,
        )
        assert create.status_code == 201, create.text
        assert create.json()["data"]["ratio"] is None

    async def test_formula_value_matches_between_get_and_aggregate(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Proves the SQL-compiled aggregate path (`sql_compiler.py`, wired
        through `resolve_column`) agrees with the Python-evaluated read path
        (`formula_service.py`) for the same data."""
        headers = await _owner_headers(client, owner_password)
        page_id = await self._staff_page(client, headers)

        rows = [
            ("1000.00", "100.00", "50.00"),
            ("2000.00", "0.00", "200.00"),
        ]
        expected_total = Decimal("0")
        for basic, ot, bonus in rows:
            resp = await client.post(
                f"/pages/{page_id}/records",
                json={
                    "occurred_at": "2026-09-07T10:00:00+05:30",
                    "data": {"basic": basic, "ot": ot, "bonus": bonus},
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            expected_total += Decimal(resp.json()["data"]["net_salary"])

        agg = await client.post(
            f"/pages/{page_id}/aggregate",
            json={"metric": "sum", "column": "net_salary"},
            headers=headers,
        )
        assert agg.status_code == 200, agg.text
        assert Decimal(agg.json()["value"]) == expected_total

    async def test_formula_is_filterable_and_sortable(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await self._staff_page(client, headers)
        for basic, ot, bonus in (("100.00", "0.00", "0.00"), ("500.00", "0.00", "0.00")):
            resp = await client.post(
                f"/pages/{page_id}/records",
                json={
                    "occurred_at": "2026-09-07T10:00:00+05:30",
                    "data": {"basic": basic, "ot": ot, "bonus": bonus},
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.text

        filtered = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "net_salary", "op": "gt", "value": "200.00"}]},
            headers=headers,
        )
        assert filtered.status_code == 200, filtered.text
        assert {i["data"]["net_salary"] for i in filtered.json()["items"]} == {"500.00"}

        sorted_desc = await client.post(
            f"/pages/{page_id}/records/query",
            json={"sort": [{"column": "net_salary", "direction": "desc"}]},
            headers=headers,
        )
        assert sorted_desc.status_code == 200, sorted_desc.text
        values = [i["data"]["net_salary"] for i in sorted_desc.json()["items"]]
        assert values == ["500.00", "100.00"]
