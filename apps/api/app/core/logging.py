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

#: What a scrubbed value is replaced with. Exported so tests assert
#: against the real marker rather than a copy that can drift from it.
REDACTED = "[redacted]"

#: Keys scrubbed from every event before it is rendered, at any depth.
_SENSITIVE_KEYS = frozenset(
    {
        # credentials and session material
        "password",
        "password_hash",
        "new_password",
        "current_password",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "jwt",
        "authorization",
        "cookie",
        "set-cookie",
        "set_cookie",
        "secret",
        "api_key",
        "apikey",
        "client_secret",
        "private_key",
        "session_id",
        # business and personal data
        "data",  # a record's business values: may hold money and personal data
        "old_data",
        "new_data",
        "diff",
        "email",
        "phone",
        "mobile",
        "nic",  # Sri Lankan national identity card number
        "address",
        "full_name",
        "account_number",
        "bank_account",
    }
)

#: How deep to walk a nested structure before giving up. Log payloads are not
#: arbitrary user data structures, and a bound is cheaper than cycle
#: detection on the logging hot path.
_MAX_SCRUB_DEPTH = 6


def _scrub_value(value: Any, depth: int) -> Any:
    """Redact sensitive keys anywhere inside a value, not just at the top.

    The previous version walked only `event_dict`'s own keys, so a nested
    payload slipped straight through: `{"record": {"data": {...}}}` logged
    every business value the `data` entry exists to redact, and an exception
    context carrying `{"payload": {"password": ...}}` logged the password.
    Nesting is the normal shape of anything interesting enough to log.
    """
    if depth > _MAX_SCRUB_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS
                else _scrub_value(item, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_scrub_value(item, depth + 1) for item in value]
    return value


def _scrub(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _scrub_value(event_dict[key], 1)
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
