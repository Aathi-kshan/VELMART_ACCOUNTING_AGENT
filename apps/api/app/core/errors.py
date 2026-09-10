"""RFC 9457 problem details (plan section 21.1).

Every error response has the same shape, so the client never has to guess:

    { "type": "https://velmart.app/errors/insufficient-permission",
      "title": "Insufficient permission",
      "status": 403,
      "detail": "Only owners can change a protected field.",
      "code": "PROTECTED_FIELD_FORBIDDEN",
      "request_id": "01J8..." }

The `code` values are the contract documented in docs/API.md section 1.4.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE_URL = "https://velmart.app/errors"
PROBLEM_CONTENT_TYPE = "application/problem+json"


def _slug(code: str) -> str:
    return code.lower().replace("_", "-")


class AppError(Exception):
    """Base class for errors that carry an HTTP status and a stable code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    title: str = "Bad request"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "PERMISSION_DENIED"
    title = "Insufficient permission"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    title = "Not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    title = "Conflict"


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "VALIDATION_FAILED"
    title = "Validation failed"


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    request: Request,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE_URL}/{_slug(code)}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            code=exc.code,
            request=request,
            extra=exc.extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            status_code=exc.status_code,
            title=str(exc.detail),
            detail=str(exc.detail),
            code="HTTP_ERROR",
            request=request,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation failed",
            detail="The request body did not match the expected schema.",
            code="VALIDATION_FAILED",
            request=request,
            # Field-level errors only. Never echo the submitted values back:
            # a rejected record payload can contain money and personal data.
            extra={
                "errors": [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ]
            },
        )
