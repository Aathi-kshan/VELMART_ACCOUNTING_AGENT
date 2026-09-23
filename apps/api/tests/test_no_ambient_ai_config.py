"""The suite must not inherit the machine's AI credentials.

Nine AI tests passed locally and failed on GitHub Actions because they depended on
configuration the developer's machine happened to have: `AI_MODEL_ROUTER` /
`AI_MODEL_DEFAULT` / `AI_MODEL_ANALYSIS` from a gitignored `apps/api/.env`, and
`OPENROUTER_API_KEY` exported in the shell. The code under test checks those before
reaching any mocked seam (`app/ai/router.py:42`, `app/ai/orchestrator.py:201`,
`app/ai/providers/openrouter.py:76`), so the gates were open locally and shut in CI.

`conftest.py`'s `_settings` fixture now clears all four for the session, and
`tests/ai/conftest.py` re-opens them with obvious non-credentials for the tests that
mean to exercise the logic behind them. This asserts the first half actually holds —
otherwise the arrangement silently degrades back to "works on the author's machine"
the next time someone exports a key.

It also pins a safety property worth having on its own: with no usable key in the
session's settings, a test that forgets to mock its transport fails with a 401 rather
than spending a real budget against a third-party API.

Deliberately lives outside `tests/ai/`, since the autouse fixture there exists
precisely to override this for that subtree.
"""

from __future__ import annotations

import pytest

_AI_CONFIG_FIELDS = (
    "OPENROUTER_API_KEY",
    "AI_MODEL_ROUTER",
    "AI_MODEL_DEFAULT",
    "AI_MODEL_ANALYSIS",
)


@pytest.mark.parametrize("field", _AI_CONFIG_FIELDS)
def test_ai_config_is_not_inherited_from_the_environment(field: str) -> None:
    from app.config import get_settings

    value = getattr(get_settings(), field)

    assert not value, (
        f"{field} is set to a real value during the test session, so this suite's "
        "result depends on the machine running it — which is how nine AI tests came "
        "to pass locally and fail in CI. A test that needs the AI config gates open "
        "should set them itself, as tests/ai/conftest.py does."
    )
