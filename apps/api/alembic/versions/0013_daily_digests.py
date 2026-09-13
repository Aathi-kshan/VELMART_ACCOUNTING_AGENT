"""daily_digests — one structured summary row per company per day

Revision ID: 0013
Revises: 0012
Create Date: P5 §nightly-ops (daily digest)

Scoped minimally: a structured JSONB summary, no delivery mechanism (no
email/push exists yet) — surfaced via `GET /dashboard/digest` and a small
banner on the audit screen (`app/tasks/daily_digest.py`, P5's nightly job).
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE daily_digests (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            digest_date DATE NOT NULL,
            summary     JSONB NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, digest_date)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_digests_company_date "
        "ON daily_digests (company_id, digest_date DESC);"
    )

    op.execute("ALTER TABLE daily_digests ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON daily_digests
          USING (company_id = current_setting('app.company_id', true)::uuid);
        """
    )
    # New tables after migration 0008's blanket grant don't inherit it —
    # each needs its own explicit GRANT (the same reason 0009/0010's own
    # tables each grant `app_user` individually too).
    op.execute("GRANT SELECT, INSERT, UPDATE ON daily_digests TO app_user;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_digests;")
