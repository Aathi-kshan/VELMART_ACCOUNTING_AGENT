"""Dashboard: `GET /reconciliation` (docs/API.md §1.8, P3.5) and configurable
widgets (plan section 15, P5).

A widget's `config` embeds the *same* filter/sort/aggregate shapes
`app/schemas/record.py` already defines (`QueryFilter`, `SortSpec`,
`AggregateMetric`, `AggregatePeriod`) rather than a second, parallel query
language — evaluation (`app/services/dashboard_service.py`) reuses
`query_service.py`'s `aggregate`/`query_records` directly for every widget
type except `TREND`, which needs day-bucketing neither of those has today.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class ReconciliationItem(BaseModel):
    business_date: date
    revenue_total: str
    ledger_total: str
    difference: str


class ReconciliationResponse(BaseModel):
    items: list[ReconciliationItem]


class DailyDigestOut(BaseModel):
    """`GET /dashboard/digest` (P5 §nightly-ops) — the structured summary
    `app/tasks/daily_digest.py` writes once per company per day. `summary`'s
    keys are the lowercased tracked audit actions plus `needs_review_count`
    — see that task's own `_TRACKED_ACTIONS`."""

    digest_date: date
    summary: dict[str, Any]
