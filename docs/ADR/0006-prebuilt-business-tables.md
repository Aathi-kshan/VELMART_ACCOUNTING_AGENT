# ADR 0006 — Six core business tables, backed natively, page engine retained

- **Status:** Accepted
- **Date:** 2026-09-10
- **Supersedes:** [ADR 0002 — No pre-built business tables](0002-no-prebuilt-business-tables.md)
- **Amends:** [ADR 0001](0001-page-engine-is-the-business-data-layer.md)
- **Deciders:** Owner
- **Related:** [PROJECT_PLAN §8.9](../PROJECT_PLAN.md), §12

## Context

[ADR 0002](0002-no-prebuilt-business-tables.md) held that Velmart ships **zero** pre-built business
tables: the Owner creates every table at runtime and all business data lives in `records.data`
JSONB. That rule was marked non-negotiable and is why the AI tools, CSV pipeline and dashboard are
all generic.

Two things pushed against it:

1. **The blank-page problem** — the top product risk in PROJECT_PLAN §28. Flexibility is worthless
   to an Owner who does not know what to build.
2. **The Owner knows exactly what this shop runs on.** Six workflows, specified down to the column:
   Employee Salary, Purchases, Expenses, Daily Revenue, Cash Ledger, Cheques. They are not
   hypotheses to be discovered through a page builder; they are the requirements.

One of them — **daily reconciliation between Daily Revenue and the Cash Ledger** — is not expressible
in the page engine at all. It compares totals across two pages for the same business date, and
cross-page rollups were explicitly deferred to V2 (§11.2).

## Decision

**Six tables ship as real, migrated, typed relational tables** with the columns in §12.1–12.6:
`employee_salaries`, `purchases`, `expenses`, `daily_revenue`, `cash_ledger`, `cheques`.
**The page engine is retained** for everything else.

**No suppliers or employees table ships.** `cheques.payee_name` and
`employee_salaries.employee_name` are plain `TEXT`, upgradable to real references if the Owner later
builds those pages and wants integrity.

Each table is kept **deliberately minimal**, and the exclusions are part of the decision:

| Table | Explicitly excluded |
|---|---|
| Employee Salary | basic salary, OT, bonus, allowances, deductions, net salary, payment status, payment method |
| Purchases | quantity, unit cost, item lines, purchase status, approval and settlement workflows |
| Expenses | a fixed category list, and any per-expense-type table |
| Daily Revenue | transaction count, returns, other sales |
| Cheques | any approval workflow beyond the protected status field |

These are not oversights to be filled in later by a well-meaning developer. They are scope.

### Shape: system pages backed by native tables

Each table is real storage, **and** is registered as a row in `pages` marked `is_system = true` with
`storage_table` naming its table, plus its `page_columns` rows:

```
pages row (is_system=true, storage_table='expenses')   <- schema descriptor
        |
        +-- page_columns rows: expense_date, expense_name, amount, ...
        |
        +-- STORAGE: native `expenses` table            <- real columns, real constraints
```

The `pages` row is metadata only. **A system page has no rows in `records`** — nothing is stored
twice. Storage dispatches on `pages.storage_table`: `NULL` means the `records` JSONB path, otherwise
the named native table.

**Why this shape:** everything already built against the page engine keeps working — generic record
endpoints, the AI tool catalogue, dynamic Flutter forms and field renderers, `page_access` grants,
protected columns, and the audit trail. Only the storage layer dispatches. The alternative — six
parallel routers, services, screens and AI tools — was rejected as roughly 6–10 extra weeks for a
worse result. Dedicated endpoints are added only where a workflow genuinely needs one, which in
practice means **reconciliation**.

### What native storage buys

Arithmetic and constraints move into the database, where they cannot be bypassed:

| §12 rule | Enforced by |
|---|---|
| `Total Revenue = Cash Sales + Card Sales` | `GENERATED ALWAYS AS ... STORED`, in `NUMERIC` |
| `Total Amount = Cash Amount + Card Sales Amount` | `GENERATED ALWAYS AS ... STORED`, in `NUMERIC` |
| Reconciliation difference | the `daily_reconciliation` view, computed on read from both tables |
| Non-negative amounts | `CHECK (... >= 0)` on every money column |
| Cheque status values | the `cheque_status` ENUM |

Both totals are generated rather than entered, so "the total doesn't match its parts" is not a class
of bug that can occur. Every figure is `NUMERIC` in Postgres and `Decimal` in Python; no monetary
value passes through a float.

## The risk this reintroduces, and how it is closed

PROJECT_PLAN §2.1 removed this arrangement because it creates **two sources of truth**: if an Owner
builds an "Expenses" page while an `expenses` table exists, two tables answer the same question and
the AI picks one.

**Mitigation — reserved page keys.** The page engine refuses to create a page whose derived key
collides with a system page, returning **409 `RESERVED_PAGE_KEY`**. The list includes singular and
plural variants — "Cheque" cannot slip past "cheques", "Salary" cannot slip past "employee_salary" —
because a near-miss name is exactly how a second source of truth would begin.
`RESERVED_PAGE_KEYS` in `app/models/business/__init__.py` is the single list.

**Mitigation — system schemas are immutable through the API.** `PATCH`/`DELETE` on a page with
`is_system = true`, and any column edit on it, are refused (409 `SYSTEM_PAGE_IMMUTABLE`). These
schemas change by migration only.

**Residual risk, accepted:** an Owner can still build a "Petty Cash" or "Vehicle Expenses" page that
overlaps a shipped table conceptually. No mechanism prevents semantic overlap; only exact and
near-miss key collision is blocked. This is a training matter.

## Consequences

**Positive**

- The Owner opens the app to six working pages covering the shop's real workflows.
- Totals are computed by the database and cannot drift; reconciliation is a view that cannot go
  stale.
- Typed columns index and aggregate natively, with no JSONB extraction.
- The page engine still covers everything unanticipated, so the flexibility thesis survives.

**Negative / accepted costs**

- **Two storage backends.** `app/repositories/records.py` dispatches on `storage_table`, and every
  read path — filter, sort, aggregate, search, CSV, AI tools — must work against both. This is the
  main new source of complexity and where bugs will concentrate.
- **Adding a column to a shipped table now needs a migration and a deploy** — exactly what the page
  engine was built to avoid. It applies to these six tables only.
- **The dual-fixture AI eval weakens as a guard.** It was designed to prove nothing is hard-coded;
  six table names legitimately now are. The eval must still pass against Owner-created pages, but it
  no longer proves generality on its own, and code review carries more of that weight.
- ~3 weeks added to the roadmap (P3.5), taking the total from ~22 to ~25 weeks.

## What remains true from ADR 0002

- **No further business tables ship.** A seventh domain is an Owner-created page, not a migration.
- The AI still discovers schema rather than assuming it: `list_pages` returns system and Owner pages
  in one list, and the tools stay generic across both. No `get_expenses()` convenience tools.
- CSV, dashboard widgets and the client field renderers stay schema-driven.
- Expense *types* remain values (`expense_name` is free text), never tables. The pressure to add a
  per-type page is the same pressure ADR 0002 existed to resist, and it is still refused.
