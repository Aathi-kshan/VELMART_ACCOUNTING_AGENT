"""Liveness and readiness (plan section 23.6, docs/API.md section 10).

Railway routes traffic to a new deployment only after /health/ready returns 200,
so a container whose migrations have not run must fail it — that is what stops a
broken build replacing a working one.

Neither endpoint leaks version or configuration detail.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import get_sessionmaker

router = APIRouter(tags=["health"])
log = get_logger(__name__)

_API_ROOT = Path(__file__).resolve().parents[2]  # apps/api/


@lru_cache
def _expected_head() -> str | None:
    """The revision this build expects the database to be at."""
    try:
        cfg = Config(str(_API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # pragma: no cover - only if the migration tree is unreadable
        log.exception("health.alembic_head_unreadable")
        return None


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    """Liveness: the process is up. Watched by the uptime monitor."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    """Readiness: the database is reachable and migrations are at head."""
    checks: dict[str, Any] = {"database": False, "migrations": False}

    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
            checks["database"] = True

            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar_one_or_none()
    except Exception:
        log.exception("health.not_ready")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    expected = _expected_head()
    checks["migrations"] = bool(expected) and current == expected

    if not checks["migrations"]:
        log.warning("health.migrations_behind", current=current, expected=expected)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    return {"status": "ready", "checks": checks}
