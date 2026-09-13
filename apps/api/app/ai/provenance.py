"""Provenance for every figure the AI states (plan sections 16.5, docs/API.md
§9): which page, how many records, and what date range — computed here from
a tool's own result, never invented by the model. Pure functions over the
plain dicts the read tools (`app/ai/tools/read_tools.py`) already return, so
this is testable without a database and will be called from the
orchestrator's response assembly once Slice 6's completion pass lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Provenance:
    page: str
    record_count: int
    date_from: str | None
    date_to: str | None

    def as_text(self) -> str:
        when = (
            "no matching records"
            if self.date_from is None
            else f"{self.date_from} to {self.date_to}"
        )
        return f"{self.record_count} record(s) in {self.page}, {when}"


def _date_range_from_items(items: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted(item["business_date"] for item in items if item.get("business_date") is not None)
    if not dates:
        return None, None
    return dates[0], dates[-1]


def provenance_for_aggregate(result: dict[str, Any]) -> Provenance:
    """`aggregate_records`' own result already carries a server-computed
    period range and record count — used directly, never re-derived."""
    period = result.get("period") or {}
    return Provenance(
        page=result["page_key"],
        record_count=result["record_count"],
        date_from=period.get("from"),
        date_to=period.get("to"),
    )


def provenance_for_records(page_key: str, items: list[dict[str, Any]]) -> Provenance:
    """`query_records`/`filter_records`/`sort_records` don't carry a
    pre-computed date range — derived here from the returned rows'
    `business_date` instead."""
    date_from, date_to = _date_range_from_items(items)
    return Provenance(page=page_key, record_count=len(items), date_from=date_from, date_to=date_to)


def provenance_for_search(matches_by_page: dict[str, list[dict[str, Any]]]) -> list[Provenance]:
    """`search_records` with no `page_key` can match on several pages at
    once — one `Provenance` per page, never collapsed into a single count
    that would hide which page(s) a figure actually came from."""
    return [provenance_for_records(page_key, items) for page_key, items in matches_by_page.items()]


def build_provenance(tool_name: str, result: dict[str, Any]) -> Provenance | list[Provenance]:
    """Dispatches to the right builder for one tool's result shape. Tools
    that never state a figure (list_pages, get_page_schema,
    get_column_values, search_entities) have no provenance to build — the
    orchestrator simply doesn't call this for those."""
    if tool_name == "aggregate_records":
        return provenance_for_aggregate(result)
    if tool_name == "search_records":
        matches_by_page = result.get("matches_by_page", {})
        return provenance_for_search(matches_by_page)
    if tool_name in ("query_records", "filter_records", "sort_records"):
        return provenance_for_records(result["page_key"], result["items"])
    raise ValueError(f"No provenance shape known for tool {tool_name!r}.")
