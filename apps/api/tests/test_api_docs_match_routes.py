"""`docs/API.md`'s permission table must name endpoints that exist.

The table listed four `/attachments/*` endpoints with ✅ permission marks. No
attachments router has ever been mounted. It also documented `GET /dashboard`
and `GET /audit`, where the real routes are `/dashboard/digest` and
`/audit-logs`, and kept widget endpoints that were later removed outright.

Nothing failed when that drifted, because the document is prose. So the drift
accumulated until an auditor read it — and a permission table that names
non-existent endpoints is worse than no table, since the natural reading is
that those endpoints exist and are secured.

This is the same idea as
`test_permissions_matrix.py::test_every_registered_endpoint_has_a_matrix_row`,
pointed at the documentation instead of the code: the table is parsed, and
every path in it must resolve to a real route.

Deliberately one-directional. It asserts the table contains nothing fictional;
it does not demand every route appear, because some (`/health`, the AI
proposal routes) are documented in their own sections rather than the table.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from app.main import create_app

# tests/ -> apps/api -> apps -> repository root
_API_DOC = Path(__file__).resolve().parents[3] / "docs" / "API.md"

#: `| **PATCH** | `/records/{id}` | ✅ | ❌ |` — method cell, then path cell.
_ROW = re.compile(r"^\|\s*\**([A-Z/ ]+?)\**\s*\|\s*`(/[^`]*)`\s*\|")


def _documented_paths() -> set[str]:
    """Every path in a permission-table row of API.md."""
    found: set[str] = set()
    for line in _API_DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match:
            found.add(match.group(2))
    return found


def _registered_paths() -> set[str]:
    """Every real route path, including those inside included routers.

    FastAPI hides an included router's routes behind `_IncludedRouter`, so a
    naive walk of `app.routes` finds almost nothing — the same trap
    `test_permissions_matrix.py` documents.
    """
    app = create_app()
    found: set[str] = set()

    def walk(routes: Iterable[Any]) -> None:
        for route in routes:
            path = getattr(route, "path", None)
            if path and getattr(route, "methods", None):
                found.add(path)
            inner = getattr(getattr(route, "original_router", None), "routes", None)
            if inner:
                walk(inner)

    walk(app.routes)
    return found


def _normalise(path: str) -> str:
    """API.md writes `{id}` where FastAPI writes the real parameter name.

    Comparing on the *shape* keeps the doc readable without letting a genuinely
    wrong path slip through: `/dashboard` and `/audit` still fail, because no
    amount of parameter renaming turns them into real routes.
    """
    return re.sub(r"\{[^}]+\}", "{}", path)


#: Paths the table documents that are not mounted, with the reason. Anything
#: here must be visibly marked as unbuilt in the document itself.
_KNOWN_UNBUILT: frozenset[str] = frozenset()


class TestDocumentedEndpointsExist:
    def test_the_table_was_parsed_at_all(self) -> None:
        """Guard against the regex silently matching nothing, which would make
        every assertion below vacuously true."""
        assert len(_documented_paths()) > 20

    @pytest.mark.parametrize("documented", sorted(_documented_paths()))
    def test_each_documented_path_is_a_real_route(self, documented: str) -> None:
        if documented in _KNOWN_UNBUILT:
            pytest.skip(f"{documented} is documented as unbuilt")
        registered = {_normalise(p) for p in _registered_paths()}
        assert _normalise(documented) in registered, (
            f"docs/API.md documents {documented!r}, which is not a registered route. "
            "Either the endpoint was removed and the table was not updated, or the "
            "table describes something that was never built."
        )


class TestRemovedFeaturesAreNotDocumentedAsLive:
    @pytest.mark.parametrize(
        "path",
        [
            "/attachments/presign",
            "/attachments/{id}/complete",
            "/dashboard/widgets/{id}",
            "/dashboard",
            "/audit",
        ],
    )
    def test_it_is_absent_from_the_permission_table(self, path: str) -> None:
        """Each of these was listed as a live, permission-checked endpoint
        while being either unbuilt or removed."""
        assert path not in _documented_paths()
