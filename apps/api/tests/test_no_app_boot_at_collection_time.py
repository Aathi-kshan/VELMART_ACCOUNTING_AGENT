"""No test module may import `app.main` at module scope.

`app/main.py` ends with `app = create_app()` — the ASGI singleton that
`uvicorn app.main:app` serves in `infra/Dockerfile.api`, `infra/docker-compose.yml`
and `infra/railway.json`. Importing the module therefore boots the application and
calls `get_settings()`, which requires `DATABASE_URL`.

pytest collects before it runs any fixture. So a module-scope import of `app.main`
demands a working `DATABASE_URL` *before* the autouse `_settings` fixture
(`conftest.py`) has pointed one at the testcontainer — and no fixture can rescue it.

That is not hypothetical. `tests/test_api_docs_match_routes.py` did exactly this and
passed 724/724 locally while aborting the entire GitHub Actions run during collection
with `Interrupted: 1 error during collection` and pytest exit code 2. It passed locally
only because a gitignored `apps/api/.env` supplies `DATABASE_URL` to every local
process, which `Settings` reads via `env_file=".env"`. The local suite cannot detect
this class of defect by running; it has to be checked structurally, which is what this
does — and why this test gives the same answer with or without a `.env` present.

`app/main.py`'s module-level `create_app()` is the only import-time settings boot in
the whole `app/` package, so matching on `app.main` alone is exact rather than a
heuristic.

Imports *inside* a function or method are the correct pattern and pass here — see
`test_permissions_matrix.py` and `conftest.py`'s `client` fixture, both of which
already do this deliberately.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent

_FORBIDDEN_MODULE = "app.main"


def _module_level_app_main_imports(tree: ast.Module) -> list[int]:
    """Line numbers of `app.main` imports at module scope.

    Only `tree.body` is walked, never recursively: an import nested in a
    function, method or class body is the pattern this test exists to
    encourage, not to flag.
    """
    lines: list[int] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(alias.name == _FORBIDDEN_MODULE for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == _FORBIDDEN_MODULE:
            lines.append(node.lineno)
    return lines


def test_no_test_module_imports_app_main_at_module_scope() -> None:
    offenders: list[str] = []
    scanned = 0

    for path in sorted(TESTS_ROOT.rglob("*.py")):
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno in _module_level_app_main_imports(tree):
            offenders.append(f"{path.relative_to(TESTS_ROOT)}:{lineno}")

    # Guard against rglob silently matching nothing, which would make the
    # assertion below vacuously true.
    assert scanned > 50, f"only {scanned} test modules scanned — the glob is wrong"

    assert not offenders, (
        "These modules import app.main at module scope, which boots the app and "
        "reads DATABASE_URL during pytest collection — before any fixture can "
        f"provision a database: {', '.join(offenders)}. Move the import inside the "
        "function that uses it, as test_permissions_matrix.py does."
    )
