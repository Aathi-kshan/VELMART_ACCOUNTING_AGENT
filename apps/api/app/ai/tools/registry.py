"""The AI tool registry — the single control point that keeps tenancy and
identity out of the model's hands (plan sections 16.2, 17.1).

Every AI tool is a plain async function that takes a `ctx: SecurityContext`
keyword-only parameter (injected by the orchestrator at call time, never
supplied by the model) plus whatever business parameters it needs, described
by a Pydantic `params_model`. `register_tool` derives the JSON schema handed
to the model from that `params_model` alone, and raises immediately if the
function forgot `ctx` or if the schema would leak `company_id`/`user_id`/
`role` — the model must never see, and therefore can never spoof, any of
these. Every later tool module (discovery_tools.py, read_tools.py,
entity_tools.py, propose_tools.py) registers through this at import time.

`kind` (P8) is what lets the orchestrator hand out the right database
session per tool: a `"read"` tool always runs on the SELECT-only `ai_reader`
session — structurally incapable of writing anything, business data or
otherwise. A `"propose"` tool runs on the RLS-armed `app_user` session
instead, since it has to INSERT an `AiProposal`/`AiProposalItem` row — but
it may still never touch a business table directly; the only path that ever
writes business data is the Owner-approved `POST /ai/proposals/{id}/apply`
endpoint, which reuses the same service functions a human `PATCH` already
calls (see `app/ai/proposals.py`).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

#: Fields that must never appear in a tool's model-facing parameter schema.
#: Any of these leaking would let the model claim to act as a different
#: tenant, user, or role than the one actually making the request.
FORBIDDEN_SCHEMA_FIELDS = frozenset({"ctx", "company_id", "user_id", "role"})

ToolKind = Literal["read", "propose"]


class ToolSchemaSafetyError(RuntimeError):
    """Raised at registration time when a tool would expose tenancy/identity
    to the model, or is missing the `ctx` parameter the orchestrator injects."""


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    params_model: type[BaseModel]
    fn: Callable[..., Awaitable[Any]]
    schema: dict[str, Any]
    kind: ToolKind = "read"


#: name -> RegisteredTool. Populated by each tool module at import time.
TOOL_REGISTRY: dict[str, RegisteredTool] = {}


def _require_ctx_parameter(name: str, fn: Callable[..., Awaitable[Any]]) -> None:
    sig = inspect.signature(fn)
    ctx_param = sig.parameters.get("ctx")
    if ctx_param is None or ctx_param.kind is not inspect.Parameter.KEYWORD_ONLY:
        raise ToolSchemaSafetyError(
            f"Tool {name!r} must accept a keyword-only `ctx: SecurityContext` "
            "parameter, injected by the orchestrator at call time — it must "
            "never be part of `params_model` or supplied by the model."
        )


def _properties_everywhere(schema: dict[str, Any]) -> set[str]:
    """Every property name anywhere in a JSON Schema, not just at the top.

    Pydantic hoists nested models into `$defs` and refers to them by `$ref`,
    so a field declared on a nested model never appears in the root
    `properties` at all. Checking only the root therefore inspected the
    shallowest possible surface: `QueryRecordsParams` already nests
    `QueryFilter` and `SortSpec` this way, so a `company_id` added to one of
    those would have passed the gate silently — and this gate is what makes
    every tool safe by construction rather than by per-tool discipline.
    """
    found: set[str] = set()
    stack: list[Any] = [schema]
    seen: list[int] = []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            # Guard against a self-referential schema ($ref cycles are legal).
            if id(node) in seen:
                continue
            seen.append(id(node))
            properties = node.get("properties")
            if isinstance(properties, dict):
                found.update(properties.keys())
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _require_no_leaked_context_fields(name: str, schema: dict[str, Any]) -> None:
    leaked = FORBIDDEN_SCHEMA_FIELDS & _properties_everywhere(schema)
    if leaked:
        raise ToolSchemaSafetyError(
            f"Tool {name!r} exposes forbidden field(s) {sorted(leaked)} in its "
            "model-facing parameter schema. SecurityContext (company_id, "
            "user_id, role) must be injected by the orchestrator, never "
            "declared on a tool's params_model."
        )


def register_tool(
    fn: Callable[..., Awaitable[Any]],
    *,
    name: str,
    description: str,
    params_model: type[BaseModel],
    kind: ToolKind = "read",
) -> RegisteredTool:
    """Register an AI tool. Raises `ToolSchemaSafetyError` immediately if the
    tool is missing `ctx` or its schema would leak tenancy/identity fields —
    this is the build-time gate that keeps every later tool safe by
    construction rather than by per-tool discipline."""
    _require_ctx_parameter(name, fn)
    schema = params_model.model_json_schema()
    _require_no_leaked_context_fields(name, schema)

    tool = RegisteredTool(
        name=name,
        description=description,
        params_model=params_model,
        fn=fn,
        schema=schema,
        kind=kind,
    )
    TOOL_REGISTRY[name] = tool
    return tool


def get_tool(name: str) -> RegisteredTool:
    try:
        return TOOL_REGISTRY[name]
    except KeyError:
        raise KeyError(f"No AI tool registered under {name!r}.") from None
