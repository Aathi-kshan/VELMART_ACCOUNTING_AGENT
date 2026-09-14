"""The OpenRouter chat-completions client (plan section 16.6). One function,
`call_model` — every other AI module that needs a model call goes through
this rather than building its own HTTP request, so there is exactly one
place that knows OpenRouter's request/response shape, tool-calling included.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings

_CHAT_COMPLETIONS_PATH = "/chat/completions"


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter is unreachable, misconfigured, or returns a
    response this client doesn't recognise."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    #: `None` when the model chose to call a tool instead of answering.
    content: str | None
    prompt_tokens: int
    completion_tokens: int
    tool_calls: list[ToolCall] = field(default_factory=list)


def _tool_schema(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """OpenAI-compatible function-tool shape, the schema OpenRouter expects."""
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> list[ToolCall]:
    if not raw:
        return []
    calls: list[ToolCall] = []
    for entry in raw:
        try:
            function = entry["function"]
            arguments = json.loads(function["arguments"]) if function.get("arguments") else {}
            calls.append(ToolCall(id=entry["id"], name=function["name"], arguments=arguments))
        except (KeyError, json.JSONDecodeError) as exc:
            raise OpenRouterError(f"Unexpected tool_call shape: {entry}") from exc
    return calls


async def call_model(
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[tuple[str, str, dict[str, Any]]] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> ModelResponse:
    """`tools`, if given, is a list of `(name, description, json_schema)` —
    the exact shape `app.ai.tools.registry.RegisteredTool` already carries,
    so a caller can pass `[(t.name, t.description, t.schema) for t in ...]`
    with no reshaping of its own."""
    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured; the AI layer cannot call a model."
        )

    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = [_tool_schema(name, desc, schema) for name, desc, schema in tools]

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
        message = body["choices"][0]["message"]
        content = message.get("content")
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response shape: {body}") from exc

    usage = body.get("usage") or {}
    return ModelResponse(
        content=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        tool_calls=_parse_tool_calls(message.get("tool_calls")),
    )
