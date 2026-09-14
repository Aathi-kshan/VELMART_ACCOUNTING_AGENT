"""Slice 9 — OpenRouter integration and cost tracking.

`call_model`'s HTTP layer is mocked here rather than hitting the real
OpenRouter API (the key configured in this environment does not
authenticate — confirmed independently with a direct curl to OpenRouter's
own `/auth/key`, not a bug in this client). The request/response shape this
client sends and parses is still exercised end-to-end; only the network
call itself is faked. Cost estimation and the daily cap need no network
access at all. The kill switch itself (`company_settings.ai_enabled`) is
enforced by the orchestrator (Slice 6), not tested here.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.costs import accumulate_cost, check_daily_cap, estimate_cost_usd, today_spend_usd
from app.ai.providers.openrouter import ModelResponse, OpenRouterError, call_model
from app.core.context import SecurityContext
from app.core.errors import AiBudgetExceededError
from app.models.ai import AiSession
from app.models.user import UserRole

_TEST_MODEL = "z-ai/glm-5.3-flash"


class TestEstimateCostUsd:
    def test_known_model_uses_its_own_price(self) -> None:
        cost = estimate_cost_usd(_TEST_MODEL, prompt_tokens=1_000_000, completion_tokens=1_000_000)

        assert cost == Decimal("0.500000")

    def test_zero_tokens_cost_nothing(self) -> None:
        assert estimate_cost_usd(_TEST_MODEL, 0, 0) == Decimal("0.000000")

    def test_unknown_model_uses_the_fallback_price(self) -> None:
        cost = estimate_cost_usd("some/unknown-model", prompt_tokens=1_000_000, completion_tokens=0)

        assert cost == Decimal("1.000000")


def _fake_post(*, status_code: int = 200, body: dict) -> object:
    async def post(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(status_code, json=body, request=httpx.Request("POST", url))

    return post


class TestCallModel:
    async def test_parses_content_and_usage_from_a_real_shaped_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            httpx.AsyncClient,
            "post",
            _fake_post(
                body={
                    "choices": [{"message": {"content": "pong"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                }
            ),
        )

        response = await call_model(
            _TEST_MODEL,
            [{"role": "user", "content": "Reply with exactly the word: pong"}],
            max_tokens=10,
        )

        assert isinstance(response, ModelResponse)
        assert response.content == "pong"
        assert response.prompt_tokens == 12
        assert response.completion_tokens == 3

    async def test_error_status_raises_a_clean_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx.AsyncClient,
            "post",
            _fake_post(
                status_code=401, body={"error": {"message": "User not found.", "code": 401}}
            ),
        )

        with pytest.raises(OpenRouterError):
            await call_model(_TEST_MODEL, [{"role": "user", "content": "hi"}])

    async def test_unexpected_response_shape_raises_a_clean_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post(body={"unexpected": "shape"}))

        with pytest.raises(OpenRouterError):
            await call_model(_TEST_MODEL, [{"role": "user", "content": "hi"}])

    async def test_missing_api_key_raises_a_clean_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)

        with pytest.raises(OpenRouterError):
            await call_model(_TEST_MODEL, [{"role": "user", "content": "hi"}])


@pytest.fixture
def owner_ctx(owner: uuid.UUID, company: uuid.UUID) -> SecurityContext:
    return SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())


async def _insert_ai_session(
    session: AsyncSession, *, company_id: uuid.UUID, user_id: uuid.UUID, cost: Decimal
) -> None:
    session.add(AiSession(company_id=company_id, user_id=user_id, total_cost_usd=cost))
    await session.commit()


class TestDailyCap:
    async def test_under_cap_does_not_raise(
        self, session: AsyncSession, owner_ctx: SecurityContext, owner: uuid.UUID
    ) -> None:
        await _insert_ai_session(
            session, company_id=owner_ctx.company_id, user_id=owner, cost=Decimal("1.00")
        )

        await check_daily_cap(session, owner_ctx, daily_cap_usd=Decimal("3.00"))

    async def test_at_or_over_cap_raises(
        self, session: AsyncSession, owner_ctx: SecurityContext, owner: uuid.UUID
    ) -> None:
        await _insert_ai_session(
            session, company_id=owner_ctx.company_id, user_id=owner, cost=Decimal("3.00")
        )

        with pytest.raises(AiBudgetExceededError):
            await check_daily_cap(session, owner_ctx, daily_cap_usd=Decimal("3.00"))

    async def test_sums_multiple_sessions_today(
        self, session: AsyncSession, owner_ctx: SecurityContext, owner: uuid.UUID
    ) -> None:
        await _insert_ai_session(
            session, company_id=owner_ctx.company_id, user_id=owner, cost=Decimal("1.50")
        )
        await _insert_ai_session(
            session, company_id=owner_ctx.company_id, user_id=owner, cost=Decimal("1.50")
        )

        spend = await today_spend_usd(session, owner_ctx)

        assert spend == Decimal("3.00")

    async def test_another_companys_spend_never_counts(
        self, session: AsyncSession, owner_ctx: SecurityContext, owner: uuid.UUID
    ) -> None:
        other_company_id = uuid.uuid4()
        from sqlalchemy import text

        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Other Co')"),
            {"id": str(other_company_id)},
        )
        await session.commit()
        await _insert_ai_session(
            session, company_id=other_company_id, user_id=owner, cost=Decimal("100.00")
        )

        spend = await today_spend_usd(session, owner_ctx)

        assert spend == Decimal("0")


class TestAccumulateCost:
    def test_adds_to_an_existing_total(self) -> None:
        ai_session = AiSession(
            company_id=uuid.uuid4(), user_id=uuid.uuid4(), total_cost_usd=Decimal("1.00")
        )

        accumulate_cost(ai_session, Decimal("0.25"))

        assert ai_session.total_cost_usd == Decimal("1.25")
