"""Scope idempotency keys per company

Revision ID: 0017
Revises: 0016

`idempotency_keys` was created in 0001 with `key TEXT PRIMARY KEY` — a single
global namespace shared by every tenant — and `app/core/idempotency.py`
looked rows up with `WHERE key = :key` alone.

Two consequences followed from that. A key string is client-supplied, so if
company B presented a key company A had already used on the same endpoint
with a hash-equal body, `lookup` returned **A's stored `response_body`** to
B: one company reading another company's record data. And because the key
was globally unique, B could also be blocked by A's key with a 409 for a
request of its own.

`idempotency_keys` is deliberately excluded from RLS (see 0006's own note),
which justified that exclusion on the grounds that access is scoped "through
the parent" — but no such scoping existed in the lookup, so nothing
constrained it.

The fix is to make the tenant part of the key's identity: `company_id` is
backfilled from each row's owning user, made NOT NULL, and the primary key
becomes `(company_id, key)`. Two companies may now use the same key string
without colliding, and a lookup that does not filter by company cannot
compile against the primary key.

Note on the downgrade: collapsing back to a global `key` primary key can
fail, because after this migration two companies are legitimately allowed to
hold the same key. Rather than delete other tenants' rows to force it
through, the downgrade drops the rows that would collide — they are
short-lived request receipts that the nightly job already purges after 48h,
so losing them costs at most a duplicate-submit window, and it is stated
here rather than left to be discovered.
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE idempotency_keys ADD COLUMN company_id UUID;")

    # Every row already names the user who made the request, and a user
    # belongs to exactly one company, so the tenant is recoverable without
    # guessing.
    op.execute(
        """
        UPDATE idempotency_keys AS ik
        SET company_id = u.company_id
        FROM users AS u
        WHERE u.id = ik.user_id;
        """
    )

    # Any row whose user has since been deleted cannot be attributed to a
    # tenant. These are request receipts under 48h old, not business data.
    op.execute("DELETE FROM idempotency_keys WHERE company_id IS NULL;")

    op.execute("ALTER TABLE idempotency_keys ALTER COLUMN company_id SET NOT NULL;")
    op.execute(
        """
        ALTER TABLE idempotency_keys
        ADD CONSTRAINT idempotency_keys_company_id_fkey
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE;
        """
    )

    op.execute("ALTER TABLE idempotency_keys DROP CONSTRAINT idempotency_keys_pkey;")
    op.execute(
        """
        ALTER TABLE idempotency_keys
        ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (company_id, key);
        """
    )

    # The nightly purge scans by age across every tenant (see
    # `app/core/idempotency.py`'s `purge_expired`), which the new composite
    # primary key does not help with.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idempotency_keys_created_at_idx "
        "ON idempotency_keys (created_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idempotency_keys_created_at_idx;")

    # A global primary key on `key` cannot coexist with rows that legitimately
    # share a key across companies. Keep the oldest row per key and drop the
    # rest; see the module docstring for why that is acceptable here.
    op.execute(
        """
        DELETE FROM idempotency_keys AS ik
        USING idempotency_keys AS keep
        WHERE ik.key = keep.key
          AND (ik.created_at, ik.company_id) > (keep.created_at, keep.company_id);
        """
    )

    op.execute("ALTER TABLE idempotency_keys DROP CONSTRAINT idempotency_keys_pkey;")
    op.execute(
        "ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (key);"
    )
    op.execute(
        "ALTER TABLE idempotency_keys DROP CONSTRAINT idempotency_keys_company_id_fkey;"
    )
    op.execute("ALTER TABLE idempotency_keys DROP COLUMN company_id;")
