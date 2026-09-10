"""ai_sessions, ai_messages, ai_proposals, ai_proposal_items + ai_reader grants

Revision ID: 0007
Revises: 0006
Create Date: plan section 8.6 / 8.8

ai_sessions and ai_proposals carry company_id (plan section 8.7's "every
tenant table") but did not exist yet when 0006_rls_policies ran, so their
RLS + tenant_isolation policy is applied here, right after CREATE TABLE.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ai_sessions (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id        UUID NOT NULL REFERENCES users(id),
            title          TEXT,
            started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            total_cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0
        );
        """
    )
    op.execute("ALTER TABLE ai_sessions ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON ai_sessions
          USING (company_id = current_setting('app.company_id', true)::uuid);
        """
    )

    op.execute(
        """
        CREATE TABLE ai_messages (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id        UUID NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
            role              TEXT NOT NULL,
            content           TEXT,
            tool_calls        JSONB,
            tool_results      JSONB,
            model             TEXT,
            prompt_tokens     INTEGER,
            completion_tokens INTEGER,
            cost_usd          NUMERIC(10,6),
            latency_ms        INTEGER,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        "CREATE TYPE proposal_status AS ENUM ('PENDING','APPLIED','CANCELLED','EXPIRED','FAILED','STALE');"
    )

    op.execute(
        """
        CREATE TABLE ai_proposals (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            session_id     UUID NOT NULL REFERENCES ai_sessions(id),
            created_by     UUID NOT NULL REFERENCES users(id),
            summary        TEXT NOT NULL,
            status         proposal_status NOT NULL DEFAULT 'PENDING',
            expires_at     TIMESTAMPTZ NOT NULL,
            applied_at     TIMESTAMPTZ,
            applied_by     UUID REFERENCES users(id),
            failure_reason TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("ALTER TABLE ai_proposals ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON ai_proposals
          USING (company_id = current_setting('app.company_id', true)::uuid);
        """
    )

    op.execute(
        """
        CREATE TABLE ai_proposal_items (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            proposal_id      UUID NOT NULL REFERENCES ai_proposals(id) ON DELETE CASCADE,
            operation        TEXT NOT NULL,
            page_id          UUID REFERENCES pages(id),
            record_id        UUID REFERENCES records(id),
            expected_version INTEGER,
            before_data      JSONB,
            after_data       JSONB NOT NULL,
            position         INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    # database roles (plan section 8.8) — finalized here, once every table exists
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_reader;")
    op.execute("REVOKE SELECT ON users, refresh_tokens, idempotency_keys FROM ai_reader;")
    op.execute("ALTER ROLE ai_reader SET statement_timeout = '8s';")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM ai_reader;")
    op.execute("DROP TABLE IF EXISTS ai_proposal_items;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_proposals;")
    op.execute("DROP TABLE IF EXISTS ai_proposals;")
    op.execute("DROP TYPE IF EXISTS proposal_status;")
    op.execute("DROP TABLE IF EXISTS ai_messages;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_sessions;")
    op.execute("DROP TABLE IF EXISTS ai_sessions;")
