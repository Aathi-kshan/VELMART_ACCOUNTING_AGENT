"""Slice 2 — the AI tool registry's schema-safety gate (plan section 17.1).

A tool's JSON schema is what the model actually sees. If `company_id`,
`user_id`, `role`, or the raw `ctx` object ever appeared in it, the model
could claim to act as a different tenant or role. `register_tool` must
refuse to register a tool that leaks any of these, and must refuse a tool
that forgot to take `ctx` as a keyword-only parameter in the first place —
both checked here with synthetic tools. The final test in this file asserts
every *real* tool registered by discovery_tools/read_tools/entity_tools
(Slices 3-5) also passes — the "CI fails the build" gate the implementation
plan names explicitly.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.ai.tools.registry import (
    TOOL_REGISTRY,
    RegisteredTool,
    ToolSchemaSafetyError,
    get_tool,
    register_tool,
)
from app.core.context import SecurityContext


@pytest.fixture(autouse=True)
def _clean_registry():
    """Tools register themselves into a module-level dict at import time;
    isolate each test from whatever other tests have registered."""
    saved = dict(TOOL_REGISTRY)
    TOOL_REGISTRY.clear()
    yield
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(saved)


class _GoodParams(BaseModel):
    page_key: str
    limit: int = 50


async def _good_tool(*, ctx: SecurityContext, params: _GoodParams) -> dict:
    return {"page_key": params.page_key, "company_id": str(ctx.company_id)}


class _LeakyParams(BaseModel):
    page_key: str
    company_id: str


async def _leaky_tool(*, ctx: SecurityContext, params: _LeakyParams) -> dict:
    return {}


class _NoCtxParams(BaseModel):
    page_key: str


async def _no_ctx_tool(params: _NoCtxParams) -> dict:
    return {}


async def _positional_ctx_tool(ctx: SecurityContext, params: _GoodParams) -> dict:
    return {}


class TestRegisterToolAcceptsWellFormedTools:
    def test_registers_and_returns_the_tool(self) -> None:
        tool = register_tool(
            _good_tool,
            name="good_tool",
            description="A well-formed tool.",
            params_model=_GoodParams,
        )

        assert isinstance(tool, RegisteredTool)
        assert tool.name == "good_tool"
        assert TOOL_REGISTRY["good_tool"] is tool
        assert get_tool("good_tool") is tool

    def test_derived_schema_matches_the_params_model(self) -> None:
        tool = register_tool(
            _good_tool,
            name="good_tool",
            description="A well-formed tool.",
            params_model=_GoodParams,
        )

        assert set(tool.schema["properties"]) == {"page_key", "limit"}
        assert tool.schema["properties"]["page_key"]["type"] == "string"

    def test_schema_never_contains_forbidden_fields(self) -> None:
        tool = register_tool(
            _good_tool,
            name="good_tool",
            description="A well-formed tool.",
            params_model=_GoodParams,
        )

        for forbidden in ("ctx", "company_id", "user_id", "role"):
            assert forbidden not in tool.schema["properties"]


class TestRegisterToolRejectsUnsafeTools:
    def test_rejects_a_params_model_that_leaks_company_id(self) -> None:
        with pytest.raises(ToolSchemaSafetyError, match="company_id"):
            register_tool(
                _leaky_tool,
                name="leaky_tool",
                description="Leaks company_id.",
                params_model=_LeakyParams,
            )
        assert "leaky_tool" not in TOOL_REGISTRY

    def test_rejects_a_tool_missing_the_ctx_parameter(self) -> None:
        with pytest.raises(ToolSchemaSafetyError, match="ctx"):
            register_tool(
                _no_ctx_tool,
                name="no_ctx_tool",
                description="Forgot ctx.",
                params_model=_NoCtxParams,
            )
        assert "no_ctx_tool" not in TOOL_REGISTRY

    def test_rejects_a_tool_where_ctx_is_positional(self) -> None:
        """`ctx` must be keyword-only so the orchestrator's call convention
        (`fn(ctx=ctx, params=params)`) can never be satisfied by a model that
        supplies its own first positional argument."""
        with pytest.raises(ToolSchemaSafetyError, match="ctx"):
            register_tool(
                _positional_ctx_tool,
                name="positional_ctx_tool",
                description="ctx is positional.",
                params_model=_GoodParams,
            )
        assert "positional_ctx_tool" not in TOOL_REGISTRY


class TestGetTool:
    def test_unknown_tool_name_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_tool("does_not_exist")


class TestEveryRegisteredToolPassesSchemaSafety:
    """The CI gate `docs/IMPLEMENTATION_PLAN.md` names explicitly: import
    every real AI tool module so it registers itself, then assert none of
    them slipped a forbidden field past `register_tool` — which would only
    be possible if a future edit bypassed `register_tool` entirely."""

    def test_all_real_tools_have_safe_schemas(self) -> None:
        import importlib

        # `_clean_registry` (autouse) wipes TOOL_REGISTRY for test isolation,
        # but a plain `import_module` no-ops on a module Python already has
        # cached — it would not re-run the `register_tool(...)` calls at
        # that module's top level. `reload` forces them to run again here.
        for module_name in (
            "app.ai.tools.discovery_tools",
            "app.ai.tools.read_tools",
            "app.ai.tools.entity_tools",
        ):
            importlib.reload(importlib.import_module(module_name))

        assert TOOL_REGISTRY, "expected at least one real AI tool to be registered"
        for tool in TOOL_REGISTRY.values():
            leaked = {"ctx", "company_id", "user_id", "role"} & tool.schema.get(
                "properties", {}
            ).keys()
            assert not leaked, f"tool {tool.name!r} leaks {leaked}"
