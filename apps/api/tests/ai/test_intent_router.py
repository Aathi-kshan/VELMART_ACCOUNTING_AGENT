"""Slice 7 — small-model intent routing.

`call_model` is mocked at the same boundary Slice 9's tests use (the
environment's configured OpenRouter key does not authenticate) — this file
exercises `classify_intent`'s own prompt-building and label-parsing logic,
not OpenRouter's actual classification accuracy, which is what Slice 14's
golden-question suite measures against a real key.
"""

from __future__ import annotations

import pytest

from app.ai import router as router_module
from app.ai.providers.openrouter import ModelResponse
from app.ai.router import RouterModelNotConfiguredError, classify_intent

_PAGES = [
    {
        "page_key": "expenses",
        "name": "Expenses",
        "description": None,
        "kind": "REGISTER",
        "record_count": 10,
        "date_range": {"from": "2026-01-01", "to": "2026-01-31"},
    }
]


def _mock_call_model(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
        return ModelResponse(content=content, prompt_tokens=20, completion_tokens=2)

    monkeypatch.setattr(router_module, "call_model", fake_call_model)


class TestClassifyIntent:
    async def test_a_business_question_routes_to_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_call_model(monkeypatch, "question")

        label = await classify_intent("How much did we spend on fuel last month?", _PAGES)

        assert label == "question"

    async def test_an_unrelated_request_routes_to_out_of_scope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_call_model(monkeypatch, "out_of_scope")

        label = await classify_intent("What's the weather like today?", _PAGES)

        assert label == "out_of_scope"

    async def test_label_parsing_tolerates_extra_whitespace_and_case(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_call_model(monkeypatch, "  Out-Of-Scope \n")

        label = await classify_intent("irrelevant", _PAGES)

        assert label == "out_of_scope"

    async def test_unrecognised_output_defaults_to_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defaulting to the read path (never silently declining) means a
        model that answers oddly still lets the Owner's real question
        through, rather than being dropped on the floor."""
        _mock_call_model(monkeypatch, "sure, here's the answer")

        label = await classify_intent("irrelevant", _PAGES)

        assert label == "question"

    async def test_missing_router_model_raises_a_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "AI_MODEL_ROUTER", None)
        monkeypatch.setattr(settings, "AI_MODEL_DEFAULT", None)

        with pytest.raises(RouterModelNotConfiguredError):
            await classify_intent("irrelevant", _PAGES)
