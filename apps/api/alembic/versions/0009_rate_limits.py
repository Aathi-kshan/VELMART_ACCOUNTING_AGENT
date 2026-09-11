"""rate_limits — Postgres-backed request throttling

Revision ID: 0009
Revises: 0008
Create Date: plan section 5.3 / 20.3

Section 5.3 puts rate limiting in Postgres ("at three users, rate limiting and
idempotency live in Postgres"; Redis only on measured contention) and section
20.3 sets the limits — 5 logins/min/IP, 100 API req/min/user — but section 8's
DDL never defined a table for it. This adds one.

A platform table, not a business table: the six of migration 0008 remain the
complete set.

Deliberately no `company_id` and no RLS. Login throttling has to work *before*
the company is known — that is the whole point of throttling a login.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE rate_limits (
            bucket_key    TEXT NOT NULL,        -- 'login:ip:<addr>' | 'api:user:<uuid>'
            window_start  TIMESTAMPTZ NOT NULL, -- start of the fixed window
            request_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (bucket_key, window_start)
        );
        """
    )
    # The nightly cleanup sweeps by window_start.
    op.execute("CREATE INDEX ix_rate_limits_window ON rate_limits (window_start);")

    # 0008's "GRANT ... ON ALL TABLES" only covered tables that existed when it
    # ran, so every table added afterwards needs its own grant — without this
    # app_user silently cannot reach the table at all.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limits TO app_user;")


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON rate_limits FROM app_user;")
    op.execute("DROP TABLE IF EXISTS rate_limits;")
