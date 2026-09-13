"""The permission matrix — plan section 4.2, in exactly one place.

This is the specification, encoded as data. `tests/test_permissions_matrix.py`
walks every row against a real request; adding an endpoint without a row here
means that test has nothing to check it against — see the "registered but
unlisted" check the test performs.

Rows marked 🟡 in section 4.2 (a role gets a *filtered* 200, never a 403) are
deliberately NOT expressible here and are NOT listed — a blanket allow/deny
rule cannot say "yes, but only rows you're assigned to." `GET /stores` is the
first such case; it has its own dedicated test
(`test_stores_manager_sees_only_assigned`) instead of a row in this matrix.

Flutter hides buttons; Flutter never decides anything. Every one of these
rules is enforced here, in FastAPI, before any database work happens.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models.user import UserRole


class Access(enum.Enum):
    #: No token required at all.
    PUBLIC = "public"
    #: Any valid, active session — owner or manager.
    AUTHENTICATED = "authenticated"
    #: Owner only; a manager token gets 403.
    OWNER_ONLY = "owner_only"


@dataclass(frozen=True, slots=True)
class PermissionRule:
    method: str
    path: str
    access: Access

    def expected_status(self, role: UserRole | None) -> int:
        """The status code this rule demands for a given caller.

        `role=None` means "no token presented at all."
        """
        if self.access is Access.PUBLIC:
            return 200
        if role is None:
            return 401
        if self.access is Access.AUTHENTICATED:
            return 200
        # OWNER_ONLY
        return 200 if role == UserRole.OWNER else 403


#: The matrix. One row per (method, path) that exists in the app today.
#: `path` must match the *real* FastAPI path param name exactly (`{user_id}`,
#: not a generic `{id}`) — `test_permissions_matrix.py`'s "every registered
#: endpoint has a matrix row" check compares against `route.path` literally.
PERMISSION_MATRIX: tuple[PermissionRule, ...] = (
    PermissionRule("GET", "/health", Access.PUBLIC),
    PermissionRule("GET", "/health/ready", Access.PUBLIC),
    PermissionRule("POST", "/auth/login", Access.PUBLIC),
    PermissionRule("POST", "/auth/refresh", Access.PUBLIC),
    PermissionRule("POST", "/auth/logout", Access.PUBLIC),
    PermissionRule("GET", "/me", Access.AUTHENTICATED),
    PermissionRule("GET", "/users", Access.OWNER_ONLY),
    PermissionRule("POST", "/users", Access.OWNER_ONLY),
    PermissionRule("PATCH", "/users/{user_id}", Access.OWNER_ONLY),
    PermissionRule("POST", "/stores", Access.OWNER_ONLY),
    PermissionRule("PATCH", "/stores/{store_id}", Access.OWNER_ONLY),
    # P3 — page/table engine (plan sections 3.10, 3.11, 10.1-10.3, 21.2)
    PermissionRule("POST", "/pages", Access.OWNER_ONLY),
    PermissionRule("PATCH", "/pages/{page_id}", Access.OWNER_ONLY),
    PermissionRule("DELETE", "/pages/{page_id}", Access.OWNER_ONLY),
    PermissionRule("POST", "/pages/{page_id}/columns", Access.OWNER_ONLY),
    PermissionRule("PATCH", "/columns/{column_id}", Access.OWNER_ONLY),
    PermissionRule("DELETE", "/columns/{column_id}", Access.OWNER_ONLY),
    PermissionRule("POST", "/columns/{column_id}/narrow-dry-run", Access.OWNER_ONLY),
    PermissionRule("PUT", "/pages/{page_id}/access", Access.OWNER_ONLY),
    PermissionRule("PATCH", "/records/{record_id}", Access.OWNER_ONLY),
    PermissionRule("DELETE", "/records/{record_id}", Access.OWNER_ONLY),
    # P3.5 — protected fields (plan section 11.4)
    PermissionRule("PATCH", "/records/{record_id}/protected-field", Access.OWNER_ONLY),
    # P3.5 Part 2 — CSV export (plan section 13.2)
    PermissionRule("POST", "/pages/{page_id}/export", Access.OWNER_ONLY),
    # P4 — ledger pages, reversal, running balance (plan section 11.5, P4 §8)
    PermissionRule("POST", "/records/{record_id}/reverse", Access.OWNER_ONLY),
    # P5 — audit log read API (plan section 18.3)
    PermissionRule("GET", "/audit-logs/export", Access.OWNER_ONLY),
    # P5 — dashboard widgets (plan section 15)
    PermissionRule("PATCH", "/dashboard/widgets/{widget_id}", Access.OWNER_ONLY),
    PermissionRule("DELETE", "/dashboard/widgets/{widget_id}", Access.OWNER_ONLY),
    PermissionRule("GET", "/dashboard/digest", Access.AUTHENTICATED),
)

#: Endpoints that exist but are intentionally absent from PERMISSION_MATRIX
#: because their rule is a data filter, not an allow/deny decision. Each one
#: MUST have its own dedicated test — see the module docstring.
CONDITIONALLY_FILTERED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET", "/stores"),
    # P3: a manager without a page grant gets 404 (not 403 — docs/API.md §1.4),
    # and POST additionally requires can_create, not just can_view — neither
    # is a plain allow/deny the matrix can express. See test_page_access_grants.
    ("GET", "/pages"),
    ("GET", "/pages/{page_id}/schema"),
    ("GET", "/pages/{page_id}/records"),
    ("POST", "/pages/{page_id}/records"),
    ("GET", "/records/{record_id}"),
    ("POST", "/pages/{page_id}/records/query"),
    ("POST", "/pages/{page_id}/aggregate"),
    ("GET", "/pages/{page_id}/column-values/{key}"),
    # P3.5: a manager needs `view` on *both* daily_revenue and cash_ledger;
    # missing either is 404, not a plain per-role allow/deny. See
    # test_reconciliation.
    ("GET", "/reconciliation"),
    # P4: same view-gated shape as query/aggregate/column-values above.
    ("GET", "/pages/{page_id}/running-balance"),
    # P5: a manager sees only entries for pages they can view, never a plain
    # per-role allow/deny. See test_audit_read_api.
    ("GET", "/audit-logs"),
    # P5: double-gated by `visible_to` (role) AND page view-access — see
    # test_dashboard_widgets.
    ("GET", "/dashboard/widgets"),
    ("GET", "/dashboard/widgets/{widget_id}/data"),
)
