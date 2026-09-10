"""Row-Level Security

Revision ID: 0006
Revises: 0005
Create Date: plan section 8.7

The API sets these with SET LOCAL inside each transaction (app/db/rls.py).
If a repository ever forgets a WHERE company_id = ..., the database still
refuses to leak. Page-level access for managers is enforced in the service
layer, where the page_access grant table lives.

tenant_isolation is applied to every table that carries its own company_id
column and already exists at this point in the migration chain.
page_columns / page_validations / page_access / user_stores / refresh_tokens
/ idempotency_keys / ai_messages / ai_proposal_items have no company_id of
their own — they are protected by CASCADE ownership through their parent
(page_id / user_id / session_id / proposal_id) plus the service-layer joins
that always scope through that parent, so they are left out of this
migration rather than approximated with an unproven join policy.

ai_sessions and ai_proposals also carry company_id but are not created until
0007_ai_tables — their RLS + tenant_isolation policy is set up there,
immediately after CREATE TABLE, instead of here.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "company_settings",
    "stores",
    "users",
    "pages",
    "records",
    "attachments",
    "import_batches",
    "dashboard_widgets",
    "audit_logs",
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (company_id = current_setting('app.company_id', true)::uuid);
            """
        )

    op.execute(
        """
        CREATE POLICY store_scope ON records
          USING (
            current_setting('app.role', true) = 'OWNER'
            OR store_id IS NULL
            OR store_id = ANY (string_to_array(current_setting('app.store_ids', true), ',')::uuid[])
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS store_scope ON records;")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
