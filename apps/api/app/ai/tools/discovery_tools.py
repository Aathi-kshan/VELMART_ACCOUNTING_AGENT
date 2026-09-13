"""Business/page and schema discovery tools (plan section 16.3, P7.3).

The AI never assumes a business's table names or columns — it must ask
first. These three tools are the only way it ever learns what pages exist
and what each looks like, all built over the same `page_service`/
`query_service` functions the rest of the app already uses; no parallel
schema-introspection logic is written here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools._shared import resolve_page
from app.ai.tools.registry import register_tool
from app.core.context import SecurityContext
from app.models.page_column import ColumnType
from app.repositories.records import base_conditions, model_for
from app.services import page_service, query_service


class ListPagesParams(BaseModel):
    pass


async def list_pages(
    *, ctx: SecurityContext, session: AsyncSession, params: ListPagesParams
) -> list[dict[str, Any]]:
    pages = await page_service.list_pages(session, ctx)
    result: list[dict[str, Any]] = []
    for page in pages:
        model = model_for(page)
        stmt = select(
            func.count(),
            func.min(model.business_date),  # type: ignore[attr-defined]
            func.max(model.business_date),  # type: ignore[attr-defined]
        ).where(*base_conditions(page))
        record_count, earliest, latest = (await session.execute(stmt)).one()
        result.append(
            {
                "page_key": page.key,
                "name": page.name,
                "description": page.description,
                "kind": page.kind.value,
                "record_count": record_count,
                "date_range": {
                    "from": earliest.isoformat() if earliest else None,
                    "to": latest.isoformat() if latest else None,
                },
            }
        )
    return result


register_tool(
    list_pages,
    name="list_pages",
    description=(
        "List every page (business table) this company has, with its name, "
        "record count, and date range. Always call this first — never "
        "assume a page's key or existence."
    ),
    params_model=ListPagesParams,
)


class GetPageSchemaParams(BaseModel):
    page_key: str = Field(description="A page key returned by list_pages.")


def _column_out(column: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": column.key,
        "name": column.name,
        "data_type": column.data_type.value,
        "is_required": column.is_required,
    }
    if column.data_type in (ColumnType.SELECT, ColumnType.MULTI_SELECT):
        out["options"] = column.config.get("options", [])
    if column.data_type is ColumnType.RECORD_REF:
        out["target_page_key"] = column.config.get("target_page_key")
    return out


async def get_page_schema(
    *, ctx: SecurityContext, session: AsyncSession, params: GetPageSchemaParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    return {
        "page_key": page.key,
        "name": page.name,
        "kind": page.kind.value,
        "columns": [_column_out(c) for c in columns],
    }


register_tool(
    get_page_schema,
    name="get_page_schema",
    description=(
        "Get the real column names, types, and options for one page, by its "
        "key. Call this before filtering, sorting, or aggregating a page you "
        "have not already inspected in this conversation."
    ),
    params_model=GetPageSchemaParams,
)


class GetColumnValuesParams(BaseModel):
    page_key: str = Field(description="A page key returned by list_pages.")
    column_key: str = Field(description="A column key returned by get_page_schema.")
    limit: int = Field(default=100, ge=1, le=500)


async def get_column_values(
    *, ctx: SecurityContext, session: AsyncSession, params: GetColumnValuesParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    values = await query_service.column_values(
        session, page, columns, params.column_key, limit=params.limit
    )
    return {"page_key": page.key, "column_key": params.column_key, "values": values}


register_tool(
    get_column_values,
    name="get_column_values",
    description=(
        "List the distinct real values seen in one column (e.g. supplier "
        "names, statuses) — use this to find the exact spelling of a value "
        "before filtering on it."
    ),
    params_model=GetColumnValuesParams,
)
