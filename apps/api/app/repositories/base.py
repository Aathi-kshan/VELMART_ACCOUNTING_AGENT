"""Tenant-scoped query helpers (plan section 20.3: repository layer scoping).

Deliberately small: two generic helpers, not a repository framework. RLS is
the second wall (migration 0006); these two functions are the first —
`app/core/permissions.py`'s matrix decides *whether* an action is allowed,
this module makes it structurally hard for a service to forget *which
company's rows* it's allowed to touch while doing it.

P3's page engine will extend this as real query needs (filtering, sorting,
pagination) arrive — this is sized for what P2 actually needs (listing users
and stores for one company), not a speculative general-purpose ORM layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


async def list_for_company[T: DeclarativeBase](
    session: AsyncSession, model: type[T], company_id: uuid.UUID
) -> list[T]:
    """Every row of `model` belonging to one company.

    `model` must declare a `company_id` column (i.e. use `TenantMixin`,
    app/db/base.py) — calling this on a table without one is a programming
    error, not a tenancy question, and SQLAlchemy will raise accordingly.
    """
    result = await session.execute(select(model).where(model.company_id == company_id))  # type: ignore[attr-defined]
    return list(result.scalars().all())


async def get_for_company[T: DeclarativeBase](
    session: AsyncSession, model: type[T], row_id: uuid.UUID, company_id: uuid.UUID
) -> T | None:
    """One row of `model`, but only if it belongs to `company_id`.

    Returns None for a row that exists but belongs to a different company —
    same as "not found" to the caller. This is the structural guard: there is
    no code path here that can return another company's row by accident.
    """
    result = await session.execute(
        select(model).where(model.id == row_id, model.company_id == company_id)  # type: ignore[attr-defined]
    )
    return result.scalar_one_or_none()
