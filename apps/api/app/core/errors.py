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

    def __init__(
        self,
        detail: str,
        *,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}
        # Response headers (e.g. Retry-After on 429) carried on the exception
        # itself. Setting them on a route's injected `Response` parameter has
        # no effect once an exception propagates: the exception handler below
        # builds a brand-new JSONResponse, discarding it. This is the only
        # path that actually reaches the client.
        self.headers = headers or {}


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


class VersionConflictError(AppError):
    """Optimistic-locking mismatch (docs/API.md §1.2) — `extra` should carry
    `{"current_version": ...}` so the caller can refetch and retry."""

    status_code = status.HTTP_409_CONFLICT
    code = "VERSION_CONFLICT"
    title = "Version conflict"


class ReservedPageKeyError(AppError):
    """plan section 10.3 / docs/API.md §1.7 — a page name derives to a key
    reserved for one of the six system pages, including singular/plural
    variants."""

    status_code = status.HTTP_409_CONFLICT
    code = "RESERVED_PAGE_KEY"
    title = "Reserved page key"


class SystemPageImmutableError(AppError):
    """docs/API.md §1.7 — a system page's schema changes only by migration."""

    status_code = status.HTTP_409_CONFLICT
    code = "SYSTEM_PAGE_IMMUTABLE"
    title = "System page is immutable"


class ColumnKeyImmutableError(AppError):
    """plan section 10.3 — `key` never changes; only `name` does."""

    status_code = status.HTTP_409_CONFLICT
    code = "COLUMN_KEY_IMMUTABLE"
    title = "Column key is immutable"


class ProtectedFieldForbiddenError(AppError):
    """plan section 11.4 / docs/API.md §1.4 — a protected column (e.g.
    `cheques.cheque_status`) is never set or changed through the generic
    create/update path, only through its dedicated endpoint, and only by an
    owner."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "PROTECTED_FIELD_FORBIDDEN"
    title = "Insufficient permission"


class ExpressionSecurityError(AppError):
    """P4 §1 — a FORMULA expression was rejected by the whitelist parser: a
    disallowed node type, an unknown function, an operand that isn't a real
    column on this page, or a length/depth cap. Raised at save time, never
    at read time."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "EXPRESSION_REJECTED"
    title = "Expression rejected"


class FormulaCycleError(AppError):
    """P4 §4 / docs/API.md §1.4 — a FORMULA column's dependency graph has a
    cycle (directly or transitively through other formula columns),
    rejected at column save time, never reaching the database."""

    status_code = status.HTTP_409_CONFLICT
    code = "FORMULA_CYCLE"
    title = "Formula cycle"


class ReferenceNotFoundError(AppError):
    """P4 §5 / docs/API.md §1.4 — a `RECORD_REF` value doesn't match any
    (non-deleted) record on its configured target page in this company.
    Never creates a stub (plan section 11.2)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "REFERENCE_NOT_FOUND"
    title = "Reference not found"


class ReferencedRecordExistsError(AppError):
    """P4 §5 / plan section 11.2 — deleting this record is blocked while
    another page's `RECORD_REF` column still points at it."""

    status_code = status.HTTP_409_CONFLICT
    code = "REFERENCED_RECORD_EXISTS"
    title = "Record is still referenced"


class LedgerRecordImmutableError(AppError):
    """P4 §8 / docs/PROJECT_PLAN.md §4.4 — a `kind = LEDGER` page's records
    are corrected by a linked reversal (`POST /records/{id}/reverse`), never
    edited in place."""

    status_code = status.HTTP_409_CONFLICT
    code = "LEDGER_RECORD_IMMUTABLE"
    title = "Ledger record is immutable"


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    request: Request,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
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
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers or None,
    )


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
            headers=exc.headers,
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
