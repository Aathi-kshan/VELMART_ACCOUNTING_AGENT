"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.db.readonly import dispose_readonly_engine
from app.db.session import dispose_engine
from app.routers import auth, health

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("api.starting", environment=settings.ENVIRONMENT.value)
    yield
    await dispose_engine()
    await dispose_readonly_engine()
    log.info("api.stopped")


def create_app() -> FastAPI:
    # Reading settings here means a missing or invalid variable fails at import
    # time, before the container is ever marked healthy.
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app_version = "0.1.0"

    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT.value,
            release=f"velmart-api@{app_version}",  # release-tagged (plan 25.1)
            send_default_pii=False,  # never ship tokens or record payloads
        )

    app = FastAPI(
        title="Velmart API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    # No CORS middleware: V1 has four native clients and no web app.

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        clear_request_context()
        bind_request_context(request_id=request_id, route=request.url.path)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "request.failed",
                method=request.method,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        if request.url.path != "/health":  # liveness polls every minute; don't log them
            log.info(
                "request.completed",
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        clear_request_context()
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
