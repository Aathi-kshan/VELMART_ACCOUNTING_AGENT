"""AI cost tracking and the daily spend cap (plan sections 16.6, 16.9).

Every model call's cost is estimated from its token usage and accumulated
onto its `AiSession`; the daily cap is checked against the company's total
spend for the current business day before a new model call is allowed. The
kill switch itself (`company_settings.ai_enabled`) is enforced by the
orchestrator (Slice 6), not here — this module only knows about money.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.dates import COMPANY_TIMEZONE
from app.core.errors import AiBudgetExceededError
from app.models.ai import AiSession

#: USD per million tokens, (prompt, completion) — deliberately small and
#: explicit rather than fetched live from OpenRouter's own pricing API;
#: update this table when the models AI_MODEL_ROUTER/DEFAULT/ANALYSIS point
#: to change.
_PRICE_PER_MILLION_TOKENS_USD: dict[str, tuple[Decimal, Decimal]] = {
    "z-ai/glm-5.3-flash": (Decimal("0.10"), Decimal("0.40")),
}
_FALLBACK_PRICE_PER_MILLION_TOKENS_USD = (Decimal("1.00"), Decimal("3.00"))


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    prompt_price, completion_price = _PRICE_PER_MILLION_TOKENS_USD.get(
        model, _FALLBACK_PRICE_PER_MILLION_TOKENS_USD
    )
    cost = (
        Decimal(prompt_tokens) * prompt_price + Decimal(completion_tokens) * completion_price
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _today_window_utc() -> tuple[datetime, datetime]:
    """The current company-local day's [start, end) in UTC — the same
    local-day convention `query_service._period_range` uses, rather than a
    UTC calendar day that would roll over mid-afternoon in Colombo."""
    tz = ZoneInfo(COMPANY_TIMEZONE)
    local_midnight = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(UTC), (local_midnight + timedelta(days=1)).astimezone(UTC)


async def today_spend_usd(session: AsyncSession, ctx: SecurityContext) -> Decimal:
    start, end = _today_window_utc()
    result = await session.execute(
        select(func.coalesce(func.sum(AiSession.total_cost_usd), 0)).where(
            AiSession.company_id == ctx.company_id,
            AiSession.started_at >= start,
            AiSession.started_at < end,
        )
    )
    return Decimal(result.scalar_one())


async def check_daily_cap(
    session: AsyncSession, ctx: SecurityContext, daily_cap_usd: Decimal
) -> None:
    spend = await today_spend_usd(session, ctx)
    if spend >= daily_cap_usd:
        raise AiBudgetExceededError(
            f"Today's AI spend (${spend}) has reached the daily cap (${daily_cap_usd})."
        )


def accumulate_cost(ai_session: AiSession, cost: Decimal) -> None:
    ai_session.total_cost_usd = (ai_session.total_cost_usd or Decimal("0")) + cost
