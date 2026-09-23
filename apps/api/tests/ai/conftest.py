"""AI tests declare the model configuration they need, rather than inheriting it.

Every test under `tests/ai/` mocks the model boundary itself — `httpx.AsyncClient.post`
(Slice 9), `router.call_model` (Slice 7), or `orchestrator.classify_intent`/`call_model`
(Slice 6). None of them wants a real provider. But the code under test checks its
configuration *before* it reaches any of those mocked seams:

- `app/ai/providers/openrouter.py:76` raises `OpenRouterError` unless `OPENROUTER_API_KEY` is set
- `app/ai/router.py:42` raises `RouterModelNotConfiguredError` unless `AI_MODEL_ROUTER`
  or `AI_MODEL_DEFAULT` is set
- `app/ai/orchestrator.py:201` short-circuits to "The AI model is not configured yet."
  (with `partial=True`, no tool calls and no proposal) unless `AI_MODEL_DEFAULT` or
  `AI_MODEL_ANALYSIS` is set

So the mocks were never reached unless the machine already had AI configuration. Nine tests
passed locally — where a gitignored `apps/api/.env` supplies `AI_MODEL_*` and the developer's
shell supplies `OPENROUTER_API_KEY` — and failed on GitHub Actions, which has neither. The
top-level `_settings` fixture now clears those four variables for the whole session, so this
fixture is what opens the gates, explicitly, for the tests that mean to exercise the logic
behind them.

The values are deliberately obvious non-credentials. Nothing here can authenticate against
OpenRouter, so a test that forgets to mock its transport fails loudly with a 401 instead of
quietly spending someone's real key.

Tests that assert the *unconfigured* behaviour
(`test_cost_control.py::test_missing_api_key_raises_a_clean_error`,
`test_intent_router.py::test_missing_router_model_raises_a_clean_error`) set the relevant
field back to `None` in their own body, which runs after this fixture and therefore wins.
"""

from __future__ import annotations

import pytest

#: Shaped like a real OpenRouter model id (`vendor/model`) because some code paths
#: use the string as a price-table key, but no such model exists.
_TEST_MODELS = {
    "AI_MODEL_ROUTER": "velmart-test/router-model",
    "AI_MODEL_DEFAULT": "velmart-test/default-model",
    "AI_MODEL_ANALYSIS": "velmart-test/analysis-model",
}


@pytest.fixture(autouse=True)
def _ai_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open the AI layer's config gates for tests that mock what lies behind them."""
    from app.config import get_settings

    # Re-fetched per test rather than captured once: `get_settings` is lru_cached and
    # at least one test elsewhere clears that cache, which would otherwise leave this
    # patching an instance the app no longer uses.
    settings = get_settings()

    monkeypatch.setattr(
        settings,
        "OPENROUTER_API_KEY",
        "not-a-real-key-tests-mock-the-transport",  # noqa: S105 - synthetic, cannot authenticate
    )
    for field, value in _TEST_MODELS.items():
        monkeypatch.setattr(settings, field, value)
