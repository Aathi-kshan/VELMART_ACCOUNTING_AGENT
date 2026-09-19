"""Slice 11 — provenance for every figure the AI states: page, record count,
date range. Pure functions over known tool-result shapes, no database.
"""

from __future__ import annotations

from app.ai.provenance import Provenance, build_provenance


class TestProvenanceForAggregate:
    def test_uses_the_aggregate_results_own_period_and_count(self) -> None:
        result = {
            "page_key": "expenses",
            "value": "587400.00",
            "record_count": 23,
            "period": {"from": "2026-09-01", "to": "2026-09-30"},
            "groups": [],
        }

        provenance = build_provenance("aggregate_records", result)

        assert provenance == Provenance(
            page="expenses", record_count=23, date_from="2026-09-01", date_to="2026-09-30"
        )

    def test_all_time_period_has_no_date_range(self) -> None:
        result = {
            "page_key": "expenses",
            "value": "0",
            "record_count": 0,
            "period": {"from": None, "to": None},
            "groups": [],
        }

        provenance = build_provenance("aggregate_records", result)

        # `aggregate_records` always yields a single Provenance, never a
        # list — narrowing what `build_provenance`'s own signature widens to
        # `Provenance | list[Provenance]` for the search-across-pages case.
        assert isinstance(provenance, Provenance)
        assert provenance.date_from is None
        assert provenance.date_to is None


class TestProvenanceForRecords:
    def test_derives_date_range_from_returned_rows(self) -> None:
        result = {
            "page_key": "fuel_log",
            "items": [
                {"business_date": "2026-01-10", "data": {}},
                {"business_date": "2026-01-05", "data": {}},
            ],
            "has_more": False,
        }

        provenance = build_provenance("query_records", result)

        assert provenance == Provenance(
            page="fuel_log", record_count=2, date_from="2026-01-05", date_to="2026-01-10"
        )

    def test_no_matching_rows_has_no_date_range(self) -> None:
        result = {"page_key": "fuel_log", "items": [], "has_more": False}

        provenance = build_provenance("filter_records", result)

        assert provenance == Provenance(
            page="fuel_log", record_count=0, date_from=None, date_to=None
        )

    def test_sort_records_uses_the_same_shape(self) -> None:
        result = {
            "page_key": "fuel_log",
            "items": [{"business_date": "2026-01-05", "data": {}}],
            "has_more": False,
        }

        provenance = build_provenance("sort_records", result)

        assert isinstance(provenance, Provenance)
        assert provenance.record_count == 1


class TestProvenanceForSearchAcrossMultiplePages:
    def test_returns_one_provenance_per_page_not_a_single_collapsed_count(self) -> None:
        result = {
            "matches_by_page": {
                "fuel_log": [{"business_date": "2026-01-05", "data": {}}],
                "expenses": [
                    {"business_date": "2026-01-03", "data": {}},
                    {"business_date": "2026-01-09", "data": {}},
                ],
            }
        }

        provenances = build_provenance("search_records", result)

        assert isinstance(provenances, list)
        by_page = {p.page: p for p in provenances}
        assert by_page["fuel_log"].record_count == 1
        assert by_page["expenses"].record_count == 2
        assert by_page["expenses"].date_from == "2026-01-03"
        assert by_page["expenses"].date_to == "2026-01-09"


class TestProvenanceAsText:
    def test_renders_a_readable_line(self) -> None:
        provenance = Provenance(
            page="expenses", record_count=23, date_from="2026-09-01", date_to="2026-09-30"
        )

        assert provenance.as_text() == "23 record(s) in expenses, 2026-09-01 to 2026-09-30"

    def test_renders_no_matching_records(self) -> None:
        provenance = Provenance(page="expenses", record_count=0, date_from=None, date_to=None)

        assert "no matching records" in provenance.as_text()
