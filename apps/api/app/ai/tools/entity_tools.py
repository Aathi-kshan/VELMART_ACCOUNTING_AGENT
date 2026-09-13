"""Entity and linked-record search (plan section 16.4, P7.5) — resolving a
name to a real store, user, or `RECORD_REF`-linked record, instead of the
model guessing or inventing an id. Store/User lookups reuse the same
company-scoping `record_service.py`'s `STORE_REF`/`USER_REF` validation
already applies; `RECORD_REF` lookups reuse `query_service.query_records`
directly, the same as the read tools.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools._shared import resolve_page
from app.ai.tools.registry import register_tool
from app.core.context import SecurityContext
from app.core.errors import ValidationFailedError
from app.models.store import Store
from app.models.user import User
from app.schemas.record import QueryRequest
from app.services import query_service


class SearchEntitiesParams(BaseModel):
    kind: Literal["store", "user", "record_ref"]
    query: str = Field(description="A name (or partial name) to match.")
    page_key: str | None = Field(
        default=None, description="Required when kind='record_ref' — the target page to search."
    )
    limit: int = Field(default=20, ge=1, le=100)


async def search_entities(
    *, ctx: SecurityContext, session: AsyncSession, params: SearchEntitiesParams
) -> dict[str, Any]:
    if params.kind == "store":
        store_stmt = (
            select(Store)
            .where(Store.company_id == ctx.company_id, Store.name.ilike(f"%{params.query}%"))
            .limit(params.limit)
        )
        stores = (await session.execute(store_stmt)).scalars().all()
        return {"matches": [{"id": str(s.id), "label": s.name, "code": s.code} for s in stores]}

    if params.kind == "user":
        user_stmt = (
            select(User)
            .where(User.company_id == ctx.company_id, User.full_name.ilike(f"%{params.query}%"))
            .limit(params.limit)
        )
        users = (await session.execute(user_stmt)).scalars().all()
        return {
            "matches": [{"id": str(u.id), "label": u.full_name, "email": u.email} for u in users]
        }

    if not params.page_key:
        raise ValidationFailedError("page_key is required when kind='record_ref'.")
    page, columns = await resolve_page(session, ctx, params.page_key)
    request = QueryRequest(search=params.query, limit=params.limit)
    result = await query_service.query_records(session, page, columns, request)
    return {
        "page_key": page.key,
        "matches": [{"id": str(item.id), "data": item.data} for item in result.items],
    }


register_tool(
    search_entities,
    name="search_entities",
    description=(
        "Resolve a name to a real store, user, or linked record — use this "
        "before filtering by a store/user/reference, to find its exact id "
        "rather than guessing."
    ),
    params_model=SearchEntitiesParams,
)
