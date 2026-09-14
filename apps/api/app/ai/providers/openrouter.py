"""The OpenRouter chat-completions client (plan section 16.6). One function,
`call_model` — every other AI module that needs a model call goes through
this rather than building its own HTTP request, so there is exactly one
place that knows OpenRouter's request/response shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

_CHAT_COMPLETIONS_PATH = "/chat/completions"


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter is unreachable, misconfigured, or returns a
    response this client doesn't recognise."""


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int


async def call_model(
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> ModelResponse:
    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured; the AI layer cannot call a model."
        )

    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.OPENROUTER_BASE_URL.rstrip("/") + _CHAT_COMPLETIONS_PATH,
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

    if response.status_code >= 400:
        raise OpenRouterError(f"OpenRouter returned {response.status_code}: {response.text}")

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response shape: {body}") from exc

    usage = body.get("usage") or {}
    return ModelResponse(
        content=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
    )
