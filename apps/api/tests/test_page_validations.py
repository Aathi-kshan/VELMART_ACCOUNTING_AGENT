"""`page_validations` — ERROR/WARNING rules over a record's own values plus
its computed FORMULA results (plan section 11.3, P4 §6). See
`test_formula_engine.py` for the formula engine itself and
`test_record_validation.py` for the write-time boundary FORMULA already
sits behind; this file is the rule-evaluation layer on top.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _create_revenue_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Revenue Check",
            "columns": [
                {"name": "Cash", "data_type": "CURRENCY", "is_required": True},
                {"name": "Card", "data_type": "CURRENCY", "is_required": True},
                {"name": "Expected", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Total",
                    "data_type": "FORMULA",
                    "config": {"expression": "cash + card"},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _add_rule(
    client: AsyncClient,
    headers: dict[str, str],
    page_id: str,
    *,
    name: str,
    expression: str,
    severity: str,
    message: str,
) -> dict:
    resp = await client.post(
        f"/pages/{page_id}/validations",
        json={
            "name": name,
            "expression": expression,
            "severity": severity,
            "message": message,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_revenue_record(
    client: AsyncClient,
    headers: dict[str, str],
    page_id: str,
    *,
    cash: str,
    card: str,
    expected: str,
) -> Response:
    return await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-07T10:00:00+05:30",
            "data": {"cash": cash, "card": card, "expected": expected},
        },
        headers=headers,
    )


class TestErrorRuleBlocksTheSave:
    async def test_balance_within_tolerance_passes(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Revenue balances",
            expression="abs(total - expected) <= 0.01",
            severity="ERROR",
            message="Revenue does not balance.",
        )

        resp = await _create_revenue_record(
            client, headers, page_id, cash="50.00", card="50.00", expected="100.00"
        )
        assert resp.status_code == 201, resp.text

    async def test_balance_at_exact_tolerance_boundary_passes(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Revenue balances",
            expression="abs(total - expected) <= 0.01",
            severity="ERROR",
            message="Revenue does not balance.",
        )

        # total = 100.00, expected = 100.01 -> diff is exactly the tolerance.
        resp = await _create_revenue_record(
            client, headers, page_id, cash="50.00", card="50.00", expected="100.01"
        )
        assert resp.status_code == 201, resp.text

    async def test_balance_just_over_tolerance_is_blocked(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Revenue balances",
            expression="abs(total - expected) <= 0.01",
            severity="ERROR",
            message="Revenue does not balance.",
        )

        # total = 100.00, expected = 100.02 -> diff exceeds the tolerance.
        resp = await _create_revenue_record(
            client, headers, page_id, cash="50.00", card="50.00", expected="100.02"
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert body["detail"] == "Revenue does not balance."


class TestWarningRuleSavesAndFlags:
    async def test_warning_saves_sets_needs_review_and_is_audited(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        company: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Unusually large revenue",
            expression="total <= 100000",
            severity="WARNING",
            message="Revenue exceeds the normal range.",
        )

        resp = await _create_revenue_record(
            client, headers, page_id, cash="60000.00", card="60000.00", expected="120000.00"
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["needs_review"] is True

        row = (
            await session.execute(
                text(
                    "SELECT new_data FROM audit_logs "
                    "WHERE company_id = :cid AND action = 'RECORD_CREATE' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"cid": str(company)},
            )
        ).one()
        assert row.new_data["validation_warnings"] == ["Revenue exceeds the normal range."]

    async def test_below_threshold_does_not_set_needs_review(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Unusually large revenue",
            expression="total <= 100000",
            severity="WARNING",
            message="Revenue exceeds the normal range.",
        )

        resp = await _create_revenue_record(
            client, headers, page_id, cash="10.00", card="10.00", expected="20.00"
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["needs_review"] is False


class TestRuleLifecycle:
    async def test_rule_referencing_an_unknown_column_is_rejected_at_save(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        resp = await client.post(
            f"/pages/{page_id}/validations",
            json={
                "name": "Bogus",
                "expression": "not_a_real_column > 0",
                "severity": "ERROR",
                "message": "x",
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "EXPRESSION_REJECTED"

    async def test_archiving_a_rule_stops_it_from_firing(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        rule = await _add_rule(
            client,
            headers,
            page_id,
            name="Revenue balances",
            expression="abs(total - expected) <= 0.01",
            severity="ERROR",
            message="Revenue does not balance.",
        )

        archive = await client.delete(f"/validations/{rule['id']}", headers=headers)
        assert archive.status_code == 200, archive.text
        assert archive.json()["is_active"] is False

        # Would have been blocked by the now-archived rule.
        resp = await _create_revenue_record(
            client, headers, page_id, cash="50.00", card="50.00", expected="999.00"
        )
        assert resp.status_code == 201, resp.text

    async def test_schema_includes_active_validations(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_revenue_page(client, headers)
        await _add_rule(
            client,
            headers,
            page_id,
            name="Revenue balances",
            expression="abs(total - expected) <= 0.01",
            severity="ERROR",
            message="Revenue does not balance.",
        )

        schema = await client.get(f"/pages/{page_id}/schema", headers=headers)
        assert schema.status_code == 200, schema.text
        names = [v["name"] for v in schema.json()["validations"]]
        assert names == ["Revenue balances"]
