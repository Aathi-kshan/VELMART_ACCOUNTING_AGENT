"""Real try-casts for JSONB values, replacing regex approximations

Revision ID: 0024
Revises: 0023

A generic page casts `data ->> key` to NUMERIC/DATE/BOOLEAN on every row, and
one unconvertible value fails the whole statement — which is how narrowing a
column's type over incompatible data bricked a page (see `_guarded_cast`).

The first fix guarded each cast with a regex. Re-auditing it showed the regex
approach cannot be made correct: `_DATE_TEXT` was unanchored and validated no
ranges, so `2024-13-01`, `2024-02-30` and `2024-01-15 <garbage>` all passed the
guard and then raised `date/time field value out of range` on `::date` — the
page bricked exactly as before, in the same scenario the guard was written for.
Anchoring it would still not reject 30 February, and every additional rule is
another chance to reject a value that is genuinely valid, which silently reads
as NULL and looks like data loss.

The question "can Postgres cast this text?" only has one reliable answer:
ask Postgres. These functions do the cast and return NULL on any failure, so a
value either converts or reads as empty, with no third outcome and nothing to
keep in sync with reality.

`IMMUTABLE` because the result depends only on the input — this lets the
planner fold them and use them in index expressions. `STRICT` so NULL in gives
NULL out without entering the block.
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_FUNCTIONS = (
    ("velmart_try_numeric", "numeric"),
    ("velmart_try_date", "date"),
    ("velmart_try_boolean", "boolean"),
)


def upgrade() -> None:
    for name, sql_type in _FUNCTIONS:
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {name}(value text) RETURNS {sql_type} AS $$
            BEGIN
                RETURN value::{sql_type};
            EXCEPTION
                WHEN others THEN
                    RETURN NULL;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE STRICT;
            """
        )
        # Read-only roles need to call these; nobody needs to redefine them.
        op.execute(f"GRANT EXECUTE ON FUNCTION {name}(text) TO app_user;")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name}(text) TO ai_reader;")


def downgrade() -> None:
    for name, _ in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}(text);")
