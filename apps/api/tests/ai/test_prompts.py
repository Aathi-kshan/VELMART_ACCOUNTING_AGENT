"""Slice 8 — schema-to-prompt rendering (plan section 16.9's cost-control
rule): the page list is always compact, a page's full schema is rendered
only once it is in play, and record data never appears in either block.
Pure functions over plain dicts, no database needed.
"""

from __future__ import annotations

from app.ai.prompts.schema_block import render_page_list_block, render_page_schema_block


class TestRenderPageListBlock:
    def test_renders_name_count_and_date_range(self) -> None:
        pages = [
            {
                "page_key": "fuel_log",
                "name": "Fuel Log",
                "description": None,
                "kind": "REGISTER",
                "record_count": 2,
                "date_range": {"from": "2026-01-05", "to": "2026-01-10"},
            }
        ]

        block = render_page_list_block(pages)

        assert "fuel_log" in block
        assert "Fuel Log" in block
        assert "2 records" in block
        assert "2026-01-05 to 2026-01-10" in block

    def test_renders_no_records_yet_when_page_is_empty(self) -> None:
        pages = [
            {
                "page_key": "empty_page",
                "name": "Empty Page",
                "description": None,
                "kind": "REGISTER",
                "record_count": 0,
                "date_range": {"from": None, "to": None},
            }
        ]

        block = render_page_list_block(pages)

        assert "no records yet" in block

    def test_empty_business_says_so(self) -> None:
        assert "no pages" in render_page_list_block([])

    def test_never_includes_record_data(self) -> None:
        """Only page-level metadata may appear here — never a row's own
        values, which would defeat the cost-control rule this block exists
        to enforce."""
        pages = [
            {
                "page_key": "fuel_log",
                "name": "Fuel Log",
                "description": None,
                "kind": "REGISTER",
                "record_count": 1,
                "date_range": {"from": "2026-01-05", "to": "2026-01-05"},
            }
        ]

        block = render_page_list_block(pages)

        assert "Van 1" not in block  # a record's own data, never rendered here


class TestRenderPageSchemaBlock:
    def test_renders_every_column_with_its_type(self) -> None:
        schema = {
            "page_key": "fuel_log",
            "name": "Fuel Log",
            "kind": "REGISTER",
            "columns": [
                {"key": "vehicle", "name": "Vehicle", "data_type": "TEXT", "is_required": True},
                {"key": "litres", "name": "Litres", "data_type": "NUMBER", "is_required": True},
                {
                    "key": "station",
                    "name": "Station",
                    "data_type": "SELECT",
                    "is_required": False,
                    "options": ["Ceypetco", "Lanka IOC"],
                },
            ],
        }

        block = render_page_schema_block(schema)

        assert "vehicle (TEXT)" in block
        assert "required" in block
        assert "options: Ceypetco, Lanka IOC" in block

    def test_renders_record_ref_target(self) -> None:
        schema = {
            "page_key": "purchases",
            "name": "Purchases",
            "kind": "REGISTER",
            "columns": [
                {
                    "key": "supplier",
                    "name": "Supplier",
                    "data_type": "RECORD_REF",
                    "is_required": False,
                    "target_page_key": "suppliers",
                },
            ],
        }

        block = render_page_schema_block(schema)

        assert "-> suppliers" in block
