"""auth_find_user_by_email / auth_find_user_by_id — pre-authentication lookups

Revision ID: 0010
Revises: 0009
Create Date: plan section 20.2 (P2 follow-up)

0006's `tenant_isolation` policy on `users` compares each row's `company_id`
against `current_setting('app.company_id', true)`. Login and refresh have no
company to set that to yet — that is exactly what they are trying to
discover, from an email or a refresh token that could belong to any tenant.
As `app_user`, that is not a corner case the app can route around: RLS
applies to every statement that role runs, without exception, so an unscoped
`SELECT ... FROM users` returns nothing at all rather than "every row."

These two functions are the narrow, audited exception. Both are `SECURITY
DEFINER`, so they run with the privileges of whichever role creates them in
this migration (the same role that owns the `users` table, and table owners
are exempt from RLS by default) rather than the privileges of `app_user`, the
caller. `SET search_path = public` is required on a `SECURITY DEFINER`
function — without it, a caller could manipulate `search_path` to shadow
`users` with an object of its own and have this function operate on that
instead. `REVOKE ALL ... FROM PUBLIC` then a single `GRANT EXECUTE TO
app_user` means no other role can call them, and they expose nothing beyond
"look up one user row" — no blanket table access.

Once `auth_service.py` has the row back, it knows the user's `company_id` and
arms the normal RLS context from it (`set_rls_context`) before running any
further query in that request. This is the same pattern
`app/dependencies/auth.py` already uses for authenticated requests, applied
one step earlier for the two requests that start with no context at all.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION auth_find_user_by_email(p_email citext)
        RETURNS SETOF users
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT * FROM users WHERE email = p_email;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION auth_find_user_by_email(citext) FROM PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION auth_find_user_by_email(citext) TO app_user;")

    op.execute(
        """
        CREATE FUNCTION auth_find_user_by_id(p_user_id uuid)
        RETURNS SETOF users
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT * FROM users WHERE id = p_user_id;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION auth_find_user_by_id(uuid) FROM PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION auth_find_user_by_id(uuid) TO app_user;")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS auth_find_user_by_id(uuid);")
    op.execute("DROP FUNCTION IF EXISTS auth_find_user_by_email(citext);")
