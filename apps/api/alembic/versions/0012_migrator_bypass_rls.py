"""migrator BYPASSRLS — nightly cross-tenant audit chain verification

Revision ID: 0012
Revises: 0011
Create Date: plan section 18.1 / P5 §nightly-ops

The audit hash chain is deliberately global across every company — the
`fn_audit_logs_hash_chain` trigger (migration 0005) has no `WHERE
company_id` in its "last row" lookup, so entries from every tenant
interleave in one sequence. Verifying it (`app/tasks/audit_chain_verify.py`)
therefore has to read every company's rows in one pass, in true insertion
order — something neither `app_user` (the app's runtime role) nor
`ai_reader` can do, since both operate under `audit_logs`'s company-scoped
`tenant_isolation` RLS policy.

`migrator` already exists (migration 0001) as the schema-owning role used at
migration time; granting it `BYPASSRLS` here is a narrow, explicit,
auditable exception for exactly this one nightly maintenance job — not a
general-purpose admin backdoor. It is never used by any request path, only
`python -m app.tasks.nightly`, connected via `DATABASE_URL_MIGRATOR`
(`app/db/migrator.py`), never the app's own `DATABASE_URL`.
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER ROLE migrator BYPASSRLS;")


def downgrade() -> None:
    op.execute("ALTER ROLE migrator NOBYPASSRLS;")
