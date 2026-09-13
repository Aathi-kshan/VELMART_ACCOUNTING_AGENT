"""The permission matrix, exercised end-to-end (plan sections 4.2, 24.2).

Two jobs:

1. `test_every_registered_endpoint_has_a_matrix_row` — the actual enforcement
   `app/core/permissions.py`'s docstring promises: a route registered on the
   app without a matching row (or an explicit CONDITIONALLY_FILTERED_ENDPOINTS
   entry) fails this test, rather than silently shipping unguarded.
2. `test_endpoint_permissions` — every (role, matrix row) combination. A
   row's `expected_status` is exact for a denial (401/403); for the allowed
   case this only asserts "not blocked" (< 400) rather than one specific 2xx,
   since the matrix encodes the permission gate's decision, not each
   endpoint's own success code (201 for a create, 204 for logout, ...) —
   those belong to that endpoint's own tests.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import (
    CONDITIONALLY_FILTERED_ENDPOINTS,
    PERMISSION_MATRIX,
    PermissionRule,
)
from app.models.user import UserRole


def _walk_routes(routes: list[Any]) -> list[Any]:
    """Flatten FastAPI's route tree. Recent FastAPI versions wrap an
    `include_router(...)` call as an opaque `_IncludedRouter` rather than
    splicing its routes directly into the parent's `.routes` — recursing into
    `.original_router.routes` is what actually gets real `APIRoute` objects
    back. Without this, every included router's endpoints are silently
    invisible to `app.routes`, and this test would pass by finding nothing
    to check at all."""
    from fastapi.routing import _IncludedRouter

    flat = []
    for route in routes:
        if isinstance(route, _IncludedRouter):
            flat.extend(_walk_routes(route.original_router.routes))
        else:
            flat.append(route)
    return flat


async def test_every_registered_endpoint_has_a_matrix_row() -> None:
    # Imported here, not at module scope: app.main builds its module-level
    # `app` singleton (and reads settings) at import time, before the
    # autouse `_settings` fixture has pointed DATABASE_URL at the container.
    from app.main import create_app

    app = create_app()
    known = {(r.method, r.path) for r in PERMISSION_MATRIX} | set(CONDITIONALLY_FILTERED_ENDPOINTS)
    # FastAPI's own doc routes, not part of the application's API surface
    # (and disabled outright in production — app/main.py).
    _framework_routes = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for route in _walk_routes(app.routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or path is None or path in _framework_routes:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            assert (method, path) in known, f"{method} {path} has no permissions matrix row"


@pytest.fixture
async def store(session: AsyncSession, company: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'S1', 'Matrix Store')"
        ),
        {"id": str(store_id), "company_id": str(company)},
    )
    await session.commit()
    return store_id


@pytest.fixture
async def page(session: AsyncSession, company: uuid.UUID, owner: uuid.UUID) -> uuid.UUID:
    page_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO pages (id, company_id, key, name, created_by) "
            "VALUES (:id, :company_id, 'matrix_page', 'Matrix Page', :owner)"
        ),
        {"id": str(page_id), "company_id": str(company), "owner": str(owner)},
    )
    await session.commit()
    return page_id


@pytest.fixture
async def page_column(session: AsyncSession, page: uuid.UUID) -> uuid.UUID:
    column_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO page_columns (id, page_id, key, name, data_type, position) "
            "VALUES (:id, :page_id, 'amount', 'Amount', 'TEXT', 0)"
        ),
        {"id": str(column_id), "page_id": str(page)},
    )
    # A protected SELECT column alongside it, purely so
    # ("PATCH", "/records/{record_id}/protected-field") has a real column to
    # target — kept separate from "amount" so every other matrix row's
    # column stays exactly TEXT, unaffected by this.
    await session.execute(
        text(
            "INSERT INTO page_columns "
            "(id, page_id, key, name, data_type, position, is_protected, config) "
            "VALUES (:id, :page_id, 'matrix_status', 'Status', 'SELECT', 1, true, "
            "CAST(:config AS jsonb))"
        ),
        {
            "id": str(uuid.uuid4()),
            "page_id": str(page),
            "config": '{"options": ["OPEN", "CLOSED"], "default": "OPEN"}',
        },
    )
    await session.commit()
    return column_id


@pytest.fixture
async def page_record(
    session: AsyncSession, company: uuid.UUID, page: uuid.UUID, owner: uuid.UUID
) -> uuid.UUID:
    record_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO records (id, company_id, page_id, occurred_at, business_date, created_by) "
            "VALUES (:id, :company_id, :page_id, now(), current_date, :owner)"
        ),
        {
            "id": str(record_id),
            "company_id": str(company),
            "page_id": str(page),
            "owner": str(owner),
        },
    )
    await session.commit()
    return record_id


@pytest.fixture
async def ledger_page(session: AsyncSession, company: uuid.UUID, owner: uuid.UUID) -> uuid.UUID:
    """A separate `kind=LEDGER` page — `POST /records/{id}/reverse` (P4 §8)
    rejects anything else, so it can't share the plain `page`/`page_record`
    fixtures every other matrix row uses."""
    page_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO pages (id, company_id, key, name, kind, created_by) "
            "VALUES (:id, :company_id, 'matrix_ledger_page', 'Matrix Ledger Page', "
            "'LEDGER', :owner)"
        ),
        {"id": str(page_id), "company_id": str(company), "owner": str(owner)},
    )
    await session.commit()
    return page_id


@pytest.fixture
async def ledger_record(
    session: AsyncSession, company: uuid.UUID, ledger_page: uuid.UUID, owner: uuid.UUID
) -> uuid.UUID:
    record_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO records (id, company_id, page_id, occurred_at, business_date, created_by) "
            "VALUES (:id, :company_id, :page_id, now(), current_date, :owner)"
        ),
        {
            "id": str(record_id),
            "company_id": str(company),
            "page_id": str(ledger_page),
            "owner": str(owner),
        },
    )
    await session.commit()
    return record_id


@pytest.fixture
async def dashboard_widget(
    session: AsyncSession, company: uuid.UUID, page: uuid.UUID, owner: uuid.UUID
) -> uuid.UUID:
    widget_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO dashboard_widgets "
            "(id, company_id, page_id, title, widget_type, config, created_by) "
            "VALUES (:id, :company_id, :page_id, 'Matrix Widget', 'LIST', '{}'::jsonb, :owner)"
        ),
        {
            "id": str(widget_id),
            "company_id": str(company),
            "page_id": str(page),
            "owner": str(owner),
        },
    )
    await session.commit()
    return widget_id


@pytest.fixture
async def validation_rule(session: AsyncSession, page: uuid.UUID) -> uuid.UUID:
    rule_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO page_validations (id, page_id, name, expression, severity, message) "
            "VALUES (:id, :page_id, 'Matrix Rule', 'True', 'WARNING', 'matrix warning')"
        ),
        {"id": str(rule_id), "page_id": str(page)},
    )
    await session.commit()
    return rule_id


@pytest.fixture
async def import_batch(
    session: AsyncSession, company: uuid.UUID, page: uuid.UUID, owner: uuid.UUID
) -> uuid.UUID:
    batch_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO import_batches "
            "(id, company_id, page_id, file_name, mapping, total_rows, status, created_by) "
            "VALUES (:id, :company_id, :page_id, 'matrix.csv', '{}'::jsonb, 0, 'COMMITTED', :owner)"
        ),
        {
            "id": str(batch_id),
            "company_id": str(company),
            "page_id": str(page),
            "owner": str(owner),
        },
    )
    await session.commit()
    return batch_id


async def _token(client: AsyncClient, email: str, password: str, *, device_id: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": device_id}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


_PATH_PARAMS = {
    "{user_id}": "manager_id",
    "{store_id}": "store_id",
    "{page_id}": "page_id",
    "{column_id}": "column_id",
    "{record_id}": "record_id",
    "{batch_id}": "batch_id",
    "{rule_id}": "rule_id",
    "{widget_id}": "widget_id",
}

#: Per-(method, path) overrides of `_PATH_PARAMS`, for a route whose
#: preconditions the shared `page`/`page_record` fixtures don't satisfy —
#: `POST /records/{id}/reverse` needs a `kind=LEDGER` page's record, not the
#: plain `kind=REGISTER` one every other `{record_id}` row shares.
_PATH_PARAMS_OVERRIDE: dict[tuple[str, str], dict[str, str]] = {
    ("POST", "/records/{record_id}/reverse"): {"{record_id}": "ledger_record_id"},
}

#: These take a multipart file rather than a JSON body — handled separately
#: in `_call` since `_BODIES` only carries JSON bodies.
_MULTIPART_ROUTES = {
    ("POST", "/pages/{page_id}/import/preview"),
    ("POST", "/pages/{page_id}/import/validate"),
    ("POST", "/pages/{page_id}/import/commit"),
}

_BODIES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", "/users"): {
        "email": "matrix-new@test.lk",
        "password": "a-strong-enough-password",
        "full_name": "Matrix New",
        "role": "MANAGER",
    },
    ("PATCH", "/users/{user_id}"): {},
    ("POST", "/stores"): {"code": "M2", "name": "Matrix New Store"},
    ("PATCH", "/stores/{store_id}"): {},
    ("POST", "/pages"): {"name": "Matrix New Page", "columns": []},
    ("PATCH", "/pages/{page_id}"): {},
    ("POST", "/pages/{page_id}/columns"): {"name": "New Column", "data_type": "TEXT"},
    ("PATCH", "/columns/{column_id}"): {"name": "Renamed"},
    ("POST", "/columns/{column_id}/narrow-dry-run"): {"data_type": "TEXT"},
    ("PUT", "/pages/{page_id}/access"): {"grants": []},
    ("PATCH", "/records/{record_id}"): {"version": 1, "data": {}},
    ("DELETE", "/records/{record_id}"): {"reason": "matrix test"},
    ("PATCH", "/records/{record_id}/protected-field"): {
        "column_key": "matrix_status",
        "value": "CLOSED",
        "version": 1,
    },
    ("POST", "/pages/{page_id}/export"): {"filters": []},
    ("POST", "/pages/{page_id}/validations"): {
        "name": "Matrix Validation",
        "expression": "amount == amount",
        "severity": "ERROR",
        "message": "matrix validation failed",
    },
    ("PATCH", "/validations/{rule_id}"): {},
    ("POST", "/records/{record_id}/reverse"): {"version": 1},
    ("POST", "/dashboard/widgets"): {
        "title": "Matrix New Widget",
        "widget_type": "LIST",
        "page_key": "matrix_page",
    },
    ("PATCH", "/dashboard/widgets/{widget_id}"): {"title": "Matrix Renamed Widget"},
}


async def _call(
    client: AsyncClient,
    rule: PermissionRule,
    role: UserRole | None,
    *,
    owner_password: str,
    manager_password: str,
    ids: dict[str, uuid.UUID],
) -> Response:
    headers: dict[str, str] = {}
    if role is UserRole.OWNER:
        token = await _token(client, "owner@test.lk", owner_password, device_id="matrix-owner")
        headers = {"Authorization": f"Bearer {token}"}
    elif role is UserRole.MANAGER:
        token = await _token(
            client, "manager@test.lk", manager_password, device_id="matrix-manager"
        )
        headers = {"Authorization": f"Bearer {token}"}

    # /auth/* endpoints authenticate via the request body, not a bearer token
    # — the header above is attached but irrelevant to them, exactly proving
    # they are PUBLIC.
    if (rule.method, rule.path) == ("POST", "/auth/login"):
        return await client.post(
            "/auth/login",
            json={
                "email": "owner@test.lk",
                "password": owner_password,
                "device_id": "matrix-login",
            },
            headers=headers,
        )
    if (rule.method, rule.path) == ("POST", "/auth/refresh"):
        login = await client.post(
            "/auth/login",
            json={
                "email": "owner@test.lk",
                "password": owner_password,
                "device_id": "matrix-refresh",
            },
        )
        return await client.post(
            "/auth/refresh",
            json={"refresh_token": login.json()["refresh_token"]},
            headers=headers,
        )
    if (rule.method, rule.path) == ("POST", "/auth/logout"):
        # logout is idempotent and accepts any token (plan section 20.2) —
        # a placeholder is enough to reach 204 regardless of role.
        return await client.post(
            "/auth/logout", json={"refresh_token": "matrix-placeholder"}, headers=headers
        )

    path = rule.path
    params = {**_PATH_PARAMS, **_PATH_PARAMS_OVERRIDE.get((rule.method, rule.path), {})}
    for placeholder, key in params.items():
        if placeholder in path:
            path = path.replace(placeholder, str(ids[key]))

    if (rule.method, rule.path) in _MULTIPART_ROUTES:
        files = {"file": ("matrix.csv", b"a,b\n1,2\n", "text/csv")}
        data = {} if rule.path.endswith("/preview") else {"payload": "{}"}
        return await client.post(path, headers=headers, files=files, data=data)

    body = _BODIES.get((rule.method, rule.path))
    return await client.request(rule.method, path, headers=headers, json=body)


@pytest.mark.parametrize("role", [None, UserRole.OWNER, UserRole.MANAGER], ids=lambda r: str(r))
@pytest.mark.parametrize("rule", list(PERMISSION_MATRIX), ids=lambda r: f"{r.method}_{r.path}")
async def test_endpoint_permissions(
    client: AsyncClient,
    rule: PermissionRule,
    role: UserRole | None,
    owner: uuid.UUID,
    manager: uuid.UUID,
    owner_password: str,
    manager_password: str,
    store: uuid.UUID,
    page: uuid.UUID,
    page_column: uuid.UUID,
    page_record: uuid.UUID,
    import_batch: uuid.UUID,
    validation_rule: uuid.UUID,
    ledger_record: uuid.UUID,
    dashboard_widget: uuid.UUID,
) -> None:
    expected = rule.expected_status(role)
    resp = await _call(
        client,
        rule,
        role,
        owner_password=owner_password,
        manager_password=manager_password,
        ids={
            "manager_id": manager,
            "store_id": store,
            "page_id": page,
            "column_id": page_column,
            "record_id": page_record,
            "batch_id": import_batch,
            "rule_id": validation_rule,
            "ledger_record_id": ledger_record,
            "widget_id": dashboard_widget,
        },
    )
    if expected >= 400:
        assert resp.status_code == expected, f"{role} {rule.method} {rule.path}: {resp.text}"
    else:
        assert resp.status_code < 400, f"{role} {rule.method} {rule.path}: {resp.text}"
