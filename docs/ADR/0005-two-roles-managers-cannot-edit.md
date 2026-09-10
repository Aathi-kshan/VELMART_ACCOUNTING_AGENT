# ADR 0005 — Exactly two roles; managers create records but never edit them

- **Status:** Accepted
- **Date:** 2026-09-10
- **Deciders:** Owner, lead developer
- **Related:** [PROJECT_PLAN §4](../PROJECT_PLAN.md), §11.4, §20.1

## Context

Earlier drafts had three roles (Owner, Manager, Viewer), a **15-minute window** during which a
manager could edit their own record, and a **correction-request queue** for changes after that
window closed.

For a shop with three people where the Owner is reachable by walking across the floor, that is a
state machine, an extra table, extra screens, and extra permission surface — all to avoid a
conversation. Every additional role multiplies the number of role × endpoint combinations that must
be specified, enforced, and tested.

## Decision

**Exactly two roles: `OWNER` and `MANAGER`.** No Viewer. No edit window. No correction queue.

| Capability | Owner | Manager |
|---|:---:|:---:|
| View permitted pages / records | ✅ all | ✅ granted only |
| Create record | ✅ | ✅ |
| **Edit existing record** | ✅ | **❌** |
| **Delete record** (soft, with reason) | ✅ | **❌** |
| **Set / change a protected column value** | ✅ | **❌** |
| Upload attachment | ✅ | ✅ |
| Delete attachment | ✅ | ❌ |
| **Create page / modify columns / formulas / validations** | ✅ | **❌** |
| **CSV import / export** | ✅ | **❌** |
| **AI — all of it** | ✅ | **❌** |
| Users, stores, settings, dashboard config | ✅ | ❌ |
| Audit log | ✅ full | 🟡 own actions only |

**A record is live the moment it is saved.** A manager who makes a mistake tells the Owner, who
edits or voids it. Every such change is audited with old and new values.

**Protected columns close the create-time loophole.** Any `SELECT` column can be marked
`is_protected`. A manager creating a record gets the configured default (e.g. `PENDING`) and
**cannot choose a different value** — attempting to returns 403. Only Owners set or change protected
values, through a dedicated endpoint, and every change writes an audit entry with action
`PROTECTED_FIELD_CHANGE`. This is the generic mechanism behind the cheque requirement: there is no
cheque module and no approval workflow — the Owner simply changes the value.

**Page-level access is default-deny.** Because the Owner invents the tables, the Owner decides which
a manager may see. `page_access` grants view and/or create rights per page. A page with **no grant
is invisible** to that manager — absent from navigation, search, CSV, and every API response. A new
page grants nothing until the Owner says so; silence is safer than accidental exposure of a Salaries
table.

**Ledger pages are corrected by reversal, not edit.** Pages created with `kind = LEDGER` are
corrected with a linked reversal record so a running balance history stays defensible.
`REGISTER` pages are edited in place by the Owner. The Owner picks per page at creation.

## Enforcement rule (non-negotiable)

This matrix lives in **exactly one place in code** — `app/core/permissions.py` — and is exercised by
an automated test that walks every role against every endpoint. Adding an endpoint without a matrix
row **fails CI**.

> **Flutter hides buttons; Flutter never decides anything.** Every permission is checked in FastAPI
> before any database work happens.

Enforcement is layered: the router guard (`require_owner`, `require_page_access`), the service layer
(where the `page_access` grant table lives), and PostgreSQL RLS behind both. Page grants are
deliberately **not** in the JWT — they are read per request, so a revoked grant takes effect
immediately. Bumping `users.token_version` invalidates every session for that user instantly.

## Consequences

**Positive**

- The permission surface is small enough to test exhaustively — and it is, at 100% of endpoints.
- A manager cannot hide a shortfall: they cannot edit, delete, or set protected values, and every
  action is audited.
- No draft state, no correction queue, no edit-window timer to reason about or debug.
- Offline is simpler: creates only. Edits need the current version and managers cannot edit anyway
  (PROJECT_PLAN §19.1).

**Negative / accepted costs**

- Every manager typo costs the Owner an interruption. This is a deliberate trade: at three users the
  Owner is reachable, and the alternative costs a workflow engine.
- Adding a Viewer role later means revisiting every matrix row and every test — accepted, because
  YAGNI at this size.
- Default-deny page access means the Owner must remember to grant access after creating a page.
  Mitigated by the launch checklist item: *"Page access grants reviewed — the manager can see
  exactly what they should."*

## Tests this ADR requires (all must be green before V1 ships)

`test_permissions_matrix` · `test_manager_cannot_edit` · `test_manager_cannot_delete` ·
`test_manager_cannot_create_pages` · `test_manager_cannot_modify_columns` ·
`test_manager_cannot_export` · `test_manager_cannot_import` · `test_manager_cannot_access_ai` ·
`test_manager_cannot_set_protected_field` · `test_owner_can_set_protected_field` ·
`test_page_access_grants` · `test_tenancy_isolation`
