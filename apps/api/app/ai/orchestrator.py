"""The AI read pipeline (plan sections 16.2, 16.9, P7.6): Owner-only
gating, execution budgets, the tool-calling loop, and conversation
persistence. Every check below runs *before* a single model call is made,
in the order a real request needs them — kill switch, rate limit, daily
cost cap — so a blocked request never spends a cent.

A provider failure (OpenRouter unreachable, misconfigured, or erroring)
is deliberately never an HTTP error: it is not an authorization or budget
problem, so it is folded into a normal assistant answer explaining the
model could not be reached, still `200 OK`. The Owner never has to handle
two different failure shapes for "the AI is temporarily unavailable".
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import costs
from app.ai.guardrails import build_tool_result_message
from app.ai.prompts.schema_block import render_page_list_block
from app.ai.provenance import Provenance, build_provenance
from app.ai.providers.openrouter import ModelResponse, OpenRouterError, ToolCall, call_model
from app.ai.router import classify_intent
from app.ai.tools import (  # noqa: F401 - populate TOOL_REGISTRY
    entity_tools,
    propose_tools,
    read_tools,
)
from app.ai.tools.discovery_tools import ListPagesParams
from app.ai.tools.discovery_tools import list_pages as list_pages_tool
from app.ai.tools.registry import TOOL_REGISTRY
from app.config import get_settings
from app.core import ratelimit
from app.core.context import SecurityContext
from app.core.dates import now_utc
from app.core.errors import AiDisabledError, AppError, NotFoundError
from app.models.ai import AiMessage, AiSession
from app.models.company import CompanySettings

_PROMPTS_DIR = Path(__file__).parent / "prompts"

#: Read-path budgets (plan section 17.4) not otherwise driven by a config
#: setting — AI_MAX_TOOL_CALLS/AI_TIMEOUT_SECONDS come from app/config.py.
MAX_TOTAL_ROWS = 2_000
MAX_TOOL_OUTPUT_TOKENS = 25_000

#: Tool names whose result carries rows countable against MAX_TOTAL_ROWS /
#: from which a Provenance can be built. Every other tool (discovery,
#: entity search) states no figure and needs neither.
_ROW_BEARING_TOOLS = frozenset({"query_records", "filter_records", "sort_records"})


class AiRateLimitedError(AppError):
    status_code = 429
    code = "AI_RATE_LIMITED"
    title = "Too many AI messages"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    answer: str
    tool_calls: list[dict[str, Any]]
    provenance: list[Provenance]
    cost_usd: Decimal
    partial: bool


@dataclass(frozen=True, slots=True)
class SendMessageResult:
    message_id: uuid.UUID
    answer: str
    tool_calls: list[dict[str, Any]]
    provenance: list[Provenance]
    cost_usd: Decimal
    partial: bool


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _row_count(tool_name: str, result: dict[str, Any]) -> int:
    if tool_name in _ROW_BEARING_TOOLS:
        return len(result.get("items", []))
    if tool_name == "search_records":
        return sum(len(v) for v in result.get("matches_by_page", {}).values())
    return 0


def _provenance_for(tool_name: str, result: dict[str, Any]) -> list[Provenance]:
    if tool_name not in (*_ROW_BEARING_TOOLS, "search_records", "aggregate_records"):
        return []
    built = build_provenance(tool_name, result)
    return built if isinstance(built, list) else [built]


@dataclass(slots=True)
class _Budgets:
    max_tool_calls: int
    timeout_seconds: int
    started_at: float = field(default_factory=time.monotonic)
    tool_calls_made: int = 0
    rows_seen: int = 0
    output_tokens_seen: int = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def timed_out(self) -> bool:
        return self.elapsed() > self.timeout_seconds

    def tool_calls_exhausted(self) -> bool:
        return self.tool_calls_made >= self.max_tool_calls

    def data_exhausted(self) -> bool:
        return self.rows_seen > MAX_TOTAL_ROWS or self.output_tokens_seen > MAX_TOOL_OUTPUT_TOKENS

    def record_tool_result(self, tool_name: str, result: dict[str, Any], content: str) -> None:
        self.tool_calls_made += 1
        self.rows_seen += _row_count(tool_name, result)
        self.output_tokens_seen += len(content) // 4  # rough estimate, no live tokenizer


def _partial_answer(reason: str, tool_calls: list[dict[str, Any]]) -> str:
    if not tool_calls:
        return f"{reason} I was not able to gather any data before stopping."
    names = ", ".join(dict.fromkeys(c["tool"] for c in tool_calls))
    return (
        f"{reason} So far I was able to call: {names}. "
        "Ask again, more narrowly, for a complete answer."
    )


async def _execute_tool_call(
    ctx: SecurityContext,
    ai_reader_session: AsyncSession,
    bookkeeping_session: AsyncSession,
    ai_session_id: uuid.UUID,
    call: ToolCall,
) -> tuple[dict[str, Any], list[Provenance]]:
    """A `"read"` tool always runs on `ai_reader_session` (SELECT-only,
    structurally incapable of writing anything). A `"propose"` tool runs on
    `bookkeeping_session` instead, since it has to INSERT its own
    `AiProposal`/`AiProposalItem` row — the only extra thing it's ever
    handed is `ai_session_id`, never business-table write access beyond
    what its own (small, reviewed) implementation does."""
    tool = TOOL_REGISTRY.get(call.name)
    if tool is None:
        return {"error": f"Unknown tool: {call.name!r}"}, []

    kwargs: dict[str, Any] = {"ctx": ctx}
    if tool.kind == "propose":
        kwargs["session"] = bookkeeping_session
        kwargs["ai_session_id"] = ai_session_id
    else:
        kwargs["session"] = ai_reader_session

    try:
        params = tool.params_model(**call.arguments)
        result = await tool.fn(params=params, **kwargs)
    except (ValidationError, AppError) as exc:
        return {"error": str(exc)}, []
    return result, _provenance_for(call.name, result)


def _tool_specs() -> list[tuple[str, str, dict[str, Any]]]:
    return [(t.name, t.description, t.schema) for t in TOOL_REGISTRY.values()]


async def run_pipeline(
    ai_reader_session: AsyncSession,
    bookkeeping_session: AsyncSession,
    ctx: SecurityContext,
    ai_session_id: uuid.UUID,
    message: str,
) -> PipelineResult:
    """The tool-calling loop itself — never raises for a provider failure,
    a budget limit, or a tool error; each becomes part of the answer. Named
    generically (not `run_read_pipeline`, its P7 name) since P8's propose
    tools run through the exact same loop, just against a different session
    — see `_execute_tool_call`."""
    settings = get_settings()
    model = settings.AI_MODEL_DEFAULT or settings.AI_MODEL_ANALYSIS
    if not model:
        return PipelineResult(
            answer="The AI model is not configured yet. Please contact support.",
            tool_calls=[],
            provenance=[],
            cost_usd=Decimal("0"),
            partial=True,
        )

    total_cost = Decimal("0")
    tool_call_log: list[dict[str, Any]] = []
    provenance: list[Provenance] = []

    try:
        pages = await list_pages_tool(ctx=ctx, session=ai_reader_session, params=ListPagesParams())
        intent = await classify_intent(message, pages)
        if intent == "out_of_scope":
            return PipelineResult(
                answer=(
                    "I can only help with questions about this business's own data — "
                    "that looks like something else."
                ),
                tool_calls=[],
                provenance=[],
                cost_usd=Decimal("0"),
                partial=False,
            )

        system_prompt = _load_prompt("system.md") + "\n\n" + _load_prompt("read_agent.md")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt + "\n\n" + render_page_list_block(pages)},
            {"role": "user", "content": message},
        ]

        budgets = _Budgets(
            max_tool_calls=settings.AI_MAX_TOOL_CALLS, timeout_seconds=settings.AI_TIMEOUT_SECONDS
        )

        while True:
            if budgets.timed_out():
                return PipelineResult(
                    answer=_partial_answer(
                        "I ran out of time gathering data for this answer.", tool_call_log
                    ),
                    tool_calls=tool_call_log,
                    provenance=provenance,
                    cost_usd=total_cost,
                    partial=True,
                )

            response: ModelResponse = await call_model(
                model, messages, tools=_tool_specs(), max_tokens=800
            )
            total_cost += costs.estimate_cost_usd(
                model, response.prompt_tokens, response.completion_tokens
            )

            if not response.tool_calls:
                return PipelineResult(
                    answer=response.content or "",
                    tool_calls=tool_call_log,
                    provenance=provenance,
                    cost_usd=total_cost,
                    partial=False,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, default=str),
                            },
                        }
                        for c in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                if budgets.tool_calls_exhausted():
                    return PipelineResult(
                        answer=_partial_answer(
                            "I reached the tool-call limit for this message before finishing.",
                            tool_call_log,
                        ),
                        tool_calls=tool_call_log,
                        provenance=provenance,
                        cost_usd=total_cost,
                        partial=True,
                    )

                call_started = time.monotonic()
                result, call_provenance = await _execute_tool_call(
                    ctx, ai_reader_session, bookkeeping_session, ai_session_id, call
                )
                duration_ms = int((time.monotonic() - call_started) * 1000)
                content = json.dumps(result, default=str)
                budgets.record_tool_result(call.name, result, content)
                tool_call_log.append({"tool": call.name, "duration_ms": duration_ms})
                provenance.extend(call_provenance)
                messages.append(
                    {**build_tool_result_message(call.name, content), "tool_call_id": call.id}
                )

                if budgets.data_exhausted():
                    return PipelineResult(
                        answer=_partial_answer(
                            "I gathered more data than I can safely process in one answer.",
                            tool_call_log,
                        ),
                        tool_calls=tool_call_log,
                        provenance=provenance,
                        cost_usd=total_cost,
                        partial=True,
                    )
    except OpenRouterError:
        return PipelineResult(
            answer="I couldn't reach the AI model provider just now. Please try again shortly.",
            tool_calls=tool_call_log,
            provenance=provenance,
            cost_usd=total_cost,
            partial=True,
        )


async def start_session(session: AsyncSession, ctx: SecurityContext) -> AiSession:
    ai_session = AiSession(company_id=ctx.company_id, user_id=ctx.user_id)
    session.add(ai_session)
    await session.flush()
    return ai_session


async def send_message(
    bookkeeping_session: AsyncSession,
    ai_reader_session: AsyncSession,
    ctx: SecurityContext,
    ai_session_id: uuid.UUID,
    message: str,
) -> SendMessageResult:
    """Owner-only gating already happened at the router (`require_owner`);
    everything here is company-level: the kill switch, the per-user rate
    limit, and the daily spend cap — checked in that order, before any
    model call, so a blocked request costs nothing."""
    ai_session = await bookkeeping_session.get(AiSession, ai_session_id)
    if ai_session is None or ai_session.company_id != ctx.company_id:
        raise NotFoundError("No such AI session.")

    settings = get_settings()
    company_settings = await bookkeeping_session.get(CompanySettings, ctx.company_id)
    ai_enabled = company_settings.ai_enabled if company_settings else True
    if not ai_enabled:
        raise AiDisabledError("AI is disabled for this company.")

    rate = await ratelimit.hit_ai_user(bookkeeping_session, ctx.user_id)
    if not rate.allowed:
        raise AiRateLimitedError(
            "Too many AI messages. Please wait and try again.",
            headers={"Retry-After": str(rate.retry_after_seconds)},
        )

    daily_cap = (
        company_settings.ai_daily_usd_cap if company_settings else settings.AI_DAILY_USD_CAP_DEFAULT
    )
    await costs.check_daily_cap(bookkeeping_session, ctx, daily_cap)

    bookkeeping_session.add(AiMessage(session_id=ai_session_id, role="user", content=message))
    await bookkeeping_session.flush()

    result = await run_pipeline(ai_reader_session, bookkeeping_session, ctx, ai_session_id, message)

    assistant_message = AiMessage(
        session_id=ai_session_id,
        role="assistant",
        content=result.answer,
        tool_calls={"calls": result.tool_calls} if result.tool_calls else None,
        cost_usd=result.cost_usd,
    )
    bookkeeping_session.add(assistant_message)
    ai_session.last_at = now_utc()
    costs.accumulate_cost(ai_session, result.cost_usd)
    await bookkeeping_session.flush()

    return SendMessageResult(
        message_id=assistant_message.id,
        answer=result.answer,
        tool_calls=result.tool_calls,
        provenance=result.provenance,
        cost_usd=result.cost_usd,
        partial=result.partial,
    )
