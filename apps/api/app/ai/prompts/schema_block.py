"""Renders discovery-tool output into compact prompt text (plan section
16.9's cost-control rule): the page **list** is always in context, a page's
full **schema** only once it is actually in play, and record **data** never
goes into the prompt directly — only through a tool call. Pure functions
over the plain dicts `discovery_tools.list_pages`/`get_page_schema` already
return, so this stays independently testable without a database.
"""

from __future__ import annotations

from typing import Any


def render_page_list_block(pages: list[dict[str, Any]]) -> str:
    """The compact, always-present page list — name, record count, date
    range. Never a column, never a record."""
    if not pages:
        return "This business has no pages yet."

    lines = ["Pages in this business:"]
    for page in pages:
        date_range = page["date_range"]
        if date_range["from"] is None:
            when = "no records yet"
        else:
            when = f"{date_range['from']} to {date_range['to']}"
        lines.append(
            f"- {page['page_key']} ({page['name']}): {page['record_count']} records, {when}"
        )
    return "\n".join(lines)


def _column_line(column: dict[str, Any]) -> str:
    parts = [f"- {column['key']} ({column['data_type']})"]
    if column.get("is_required"):
        parts.append("required")
    if column.get("options"):
        parts.append(f"options: {', '.join(column['options'])}")
    if column.get("target_page_key"):
        parts.append(f"-> {column['target_page_key']}")
    return " ".join(parts)


def render_page_schema_block(schema: dict[str, Any]) -> str:
    """The full column list for one page — only rendered once that page is
    actually in play for the current question, per the cost-control rule."""
    lines = [f"Schema for page '{schema['page_key']}' ({schema['name']}):"]
    lines.extend(_column_line(c) for c in schema["columns"])
    return "\n".join(lines)
