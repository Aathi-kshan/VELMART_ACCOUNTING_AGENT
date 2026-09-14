"""Small-model intent routing (plan section 16.7). A cheap model classifies
the Owner's message before any expensive tool-calling loop starts — a
simple lookup shouldn't pay for the same processing as a multi-page
analysis. P8 adds a third label ('change_request'); P7 only ever routes to
'question' (the read path) or 'out_of_scope' (a polite decline).
"""

from __future__ import annotations

from typing import Any, Literal

from app.ai.prompts.schema_block import render_page_list_block
from app.ai.providers.openrouter import call_model
from app.config import get_settings

IntentLabel = Literal["question", "out_of_scope"]

_ROUTER_SYSTEM_PROMPT = (
    "Classify the Owner's message into exactly one label: 'question' if it "
    "asks about this business's own data (lookups, totals, trends, "
    "comparisons), or 'out_of_scope' if it asks for something this "
    "business-data assistant cannot help with (general knowledge, unrelated "
    "topics, or a request to change data). Reply with exactly one word — "
    "question or out_of_scope — and nothing else."
)


class RouterModelNotConfiguredError(RuntimeError):
    """Raised when AI_MODEL_ROUTER (and its AI_MODEL_DEFAULT fallback) are
    both unset — intent routing cannot run without a model to call."""


def _parse_label(raw: str) -> IntentLabel:
    normalised = raw.strip().lower().replace("-", "_")
    if "out_of_scope" in normalised:
        return "out_of_scope"
    return "question"


async def classify_intent(message: str, pages: list[dict[str, Any]]) -> IntentLabel:
    settings = get_settings()
    model = settings.AI_MODEL_ROUTER or settings.AI_MODEL_DEFAULT
    if not model:
        raise RouterModelNotConfiguredError(
            "Neither AI_MODEL_ROUTER nor AI_MODEL_DEFAULT is configured."
        )

    context = render_page_list_block(pages)
    response = await call_model(
        model,
        [
            {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nOwner's message: {message}"},
        ],
        max_tokens=10,
    )
    return _parse_label(response.content)
