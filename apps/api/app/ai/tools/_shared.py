"""Helpers shared by discovery_tools.py, read_tools.py, and entity_tools.py.

Every AI tool takes a `page_key` (never a raw page id) and resolves it
generically through `page_service` — there is exactly one place a tool
turns a model-supplied string into a real `Page` row, so a bad key always
produces the same clean error rather than each tool inventing its own.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.models.page import Page
from app.models.page_column import PageColumn
from app.services import page_service


async def resolve_page(
    session: AsyncSession, ctx: SecurityContext, page_key: str
) -> tuple[Page, list[PageColumn]]:
    """`page_key` -> `(Page, columns)`, or a clean `NotFoundError` — never a
    raw SQL error, and never a hardcoded assumption about which pages exist
    for this business."""
    page = await page_service.get_page_by_key(session, ctx.company_id, page_key)
    if page is None or page.is_archived:
        raise NotFoundError(f"No such page: {page_key!r}")
    return await page_service.get_page_schema(session, ctx, page.id)
