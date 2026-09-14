"""Slice 6 — the Owner-only `/ai/sessions` API's gating, execution budgets,
and persistence. `call_model`/`classify_intent` are mocked at the
orchestrator's own imported names (the same boundary Slices 7/9 use) so
these tests never depend on a live model provider — they check the
orchestrator's control flow, not answer quality (that's Slice 14's job).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import orchestrator as orchestrator_module
from app.ai.providers.openrouter import ModelResponse, ToolCall
from app.core import ratelimit


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ai_session_id(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> uuid.UUID:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post("/ai/sessions", headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


def _mock_final_answer(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    async def fake_classify_intent(*args: object, **kwargs: object) -> str:
        return "question"

    async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
        return ModelResponse(content=content, prompt_tokens=10, completion_tokens=5, tool_calls=[])

    monkeypatch.setattr(orchestrator_module, "classify_intent", fake_classify_intent)
    monkeypatch.setattr(orchestrator_module, "call_model", fake_call_model)


class TestAiDisabledKillSwitch:
    async def test_ai_disabled_blocks_the_next_message(
        self,
        client: AsyncClient,
        owner_password: str,
        company: uuid.UUID,
        session: AsyncSession,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_final_answer(monkeypatch, "should never be reached")
        await session.execute(
            text(
                "INSERT INTO company_settings (company_id, ai_enabled) VALUES (:cid, false) "
                "ON CONFLICT (company_id) DO UPDATE SET ai_enabled = false"
            ),
            {"cid": str(company)},
        )
        await session.commit()
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )

        assert resp.status_code == 403
        assert resp.json()["code"] == "AI_DISABLED"


class TestRateLimit:
    async def test_exceeding_the_rate_limit_returns_429(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        session: AsyncSession,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_final_answer(monkeypatch, "should never be reached")
        for _ in range(ratelimit.AI_MESSAGES_PER_5_MIN):
            result = await ratelimit.hit_ai_user(session, owner)
            assert result.allowed
        await session.commit()
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "One too many."},
            headers=headers,
        )

        assert resp.status_code == 429
        assert resp.json()["code"] == "AI_RATE_LIMITED"
        assert "Retry-After" in resp.headers


class TestDailyCap:
    async def test_exceeding_the_daily_cap_blocks_the_message(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        company: uuid.UUID,
        owner_password: str,
        session: AsyncSession,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.models.ai import AiSession

        _mock_final_answer(monkeypatch, "should never be reached")
        session.add(AiSession(company_id=company, user_id=owner, total_cost_usd=Decimal("3.00")))
        await session.commit()
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )

        assert resp.status_code == 402
        assert resp.json()["code"] == "AI_BUDGET_EXCEEDED"


class TestToolCallBudget:
    async def test_exceeding_the_tool_call_limit_returns_a_partial_answer(
        self,
        client: AsyncClient,
        owner_password: str,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "AI_MAX_TOOL_CALLS", 2)

        async def fake_classify_intent(*args: object, **kwargs: object) -> str:
            return "question"

        async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
            # Never converges — always asks for one more tool call, forcing
            # the loop to hit the budget rather than finish naturally.
            return ModelResponse(
                content=None,
                prompt_tokens=10,
                completion_tokens=5,
                tool_calls=[ToolCall(id="call_1", name="list_pages", arguments={})],
            )

        monkeypatch.setattr(orchestrator_module, "classify_intent", fake_classify_intent)
        monkeypatch.setattr(orchestrator_module, "call_model", fake_call_model)
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["partial"] is True
        assert len(body["tool_calls"]) == 2
        assert "tool-call limit" in body["answer"]


class TestOutOfScope:
    async def test_out_of_scope_message_is_declined_without_tool_calls(
        self,
        client: AsyncClient,
        owner_password: str,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_classify_intent(*args: object, **kwargs: object) -> str:
            return "out_of_scope"

        called = False

        async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
            nonlocal called
            called = True
            raise AssertionError("call_model should never run for an out-of-scope message")

        monkeypatch.setattr(orchestrator_module, "classify_intent", fake_classify_intent)
        monkeypatch.setattr(orchestrator_module, "call_model", fake_call_model)
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "What's the weather today?"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["partial"] is False
        assert not called


class TestPersistence:
    async def test_user_and_assistant_messages_persist(
        self,
        client: AsyncClient,
        owner_password: str,
        session: AsyncSession,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_final_answer(monkeypatch, "Total spend was Rs. 1,000.")
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        rows = (
            await session.execute(
                text(
                    "SELECT role, content FROM ai_messages "
                    "WHERE session_id = :sid ORDER BY created_at"
                ),
                {"sid": str(ai_session_id)},
            )
        ).all()
        assert [r.role for r in rows] == ["user", "assistant"]
        assert rows[0].content == "How much did we spend last month?"
        assert rows[1].content == "Total spend was Rs. 1,000."

    async def test_provider_failure_is_a_200_with_a_graceful_answer(
        self, client: AsyncClient, owner_password: str, ai_session_id: uuid.UUID
    ) -> None:
        """No mocking here — this exercises the real (broken, per
        environment) OpenRouter key, proving a provider outage never
        surfaces as an HTTP error to the Owner."""
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["partial"] is True
        assert body["answer"] != ""
