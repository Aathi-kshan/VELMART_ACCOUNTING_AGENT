"""Anchor the audit chain head so truncation is detectable

Revision ID: 0019
Revises: 0018

The hash chain proves that no row *between* two others was altered, because
each row's hash feeds the next. It proves nothing about the end of the chain:
delete the newest `k` rows and what remains is still internally consistent and
verifies clean. Deleting the most recent entries is also the obvious move for
anyone covering their tracks, so the one thing the chain could not detect was
the most likely thing to happen to it.

This records where the chain reached the last time it verified successfully:
the highest row's `id` and `row_hash`, plus the total row count. A later run
compares against it — if the anchored row has vanished, or its hash no longer
matches, or the table now holds fewer rows than it did, the log has been
truncated or rewritten even though the surviving chain links up.

`app_user` is deliberately granted nothing here. The application never reads
or writes this table; only the `migrator` role that runs the nightly
verification does. An attacker limited to the application's own database role
therefore cannot move the anchor to match a truncation they just performed,
which is the whole point of keeping it outside `audit_logs`.
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `only_row` makes this a single-row table by construction: the CHECK
    # allows just one value and it is the primary key, so a second INSERT
    # collides rather than silently creating a rival anchor.
    op.execute(
        """
        CREATE TABLE audit_chain_anchor (
            only_row      BOOLEAN PRIMARY KEY DEFAULT true CHECK (only_row),
            last_id       BIGINT NOT NULL,
            last_row_hash TEXT NOT NULL,
            row_count     BIGINT NOT NULL,
            verified_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON audit_chain_anchor FROM app_user;")
    op.execute("REVOKE ALL PRIVILEGES ON audit_chain_anchor FROM ai_reader;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_chain_anchor;")
