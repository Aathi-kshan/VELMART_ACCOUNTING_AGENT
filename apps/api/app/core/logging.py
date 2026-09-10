"""Structured JSON logging (plan section 25.1).

Every line carries `request_id`, and — once auth exists — `company_id`, `user_id`,
`page_id`, `route` and `duration_ms`.

Two rules from section 20.3 that this module exists to keep:
  * never log tokens, passwords, or full record payloads
  * no money values at INFO level
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

#: Keys scrubbed from every event before it is rendered.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "jwt",
        "authorization",
        "secret",
        "api_key",
        "data",  # a record's business values: may hold money and personal data
    }
)


def _scrub(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _scrub,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """Bind values onto every log line for the rest of this request."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
