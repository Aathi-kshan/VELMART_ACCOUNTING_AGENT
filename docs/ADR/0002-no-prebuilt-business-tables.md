# ADR 0002 — Velmart ships with no pre-built business tables

> ## ⚠️ SUPERSEDED by [ADR 0006](0006-prebuilt-business-tables.md) (2026-09-10)
>
> Six core tables — employee salary, purchases, expenses, daily revenue, cash ledger and cheques —
> now ship as real relational tables. The page engine is retained for everything else, and the
> duplicate-page failure mode described below is closed structurally by reserved page keys.
>
> **The reasoning below is kept as history — it is why the rule existed and what it was protecting
> against. Read it before proposing a seventh pre-built table.**

- **Status:** ~~Accepted — non-negotiable~~ → **Superseded by ADR 0006**
- **Date:** 2026-09-10
- **Deciders:** Owner, lead developer
- **Related:** [ADR 0001](0001-page-engine-is-the-business-data-layer.md), [ADR 0006](0006-prebuilt-business-tables.md), [PROJECT_PLAN §1.2](../PROJECT_PLAN.md), §3.3, §31

## Context

Accounting products traditionally ship fixed modules: an Expenses screen, a Salaries screen, a
Cheques screen. Each module presumes it knows how the business works.

This business already has its own structure, expressed today in spreadsheets. A fixed module forces
that structure to be re-expressed in someone else's shape, and every mismatch becomes either a
workaround in a Notes field or a feature request. Worse, when a fixed module and an Owner-created
page describe the same thing, the system holds two answers to one question
(see [ADR 0001](0001-page-engine-is-the-business-data-layer.md)).

## Decision

**Velmart V1 ships with zero pre-built business pages.**

There is no Expenses module, no Salaries module, no Revenue module, no Cheques module, no Cash
Ledger module, no Suppliers module — **not in the database, not in the API, not in the client, and
not in the AI tools.**

The Owner creates every business table: names it, defines every column and its type, decides what is
required, writes the formulas, and marks which columns are protected. The platform supplies only the
engine underneath — storage, typing, validation, calculation, permissions, audit, attachments, CSV,
offline capture, and AI.

This forces a specific shape on every feature that touches business data:

| Feature | Consequence of this decision |
|---|---|
| Column types | `RECORD_REF` with a configurable `target_page_key`, **not** `SUPPLIER_REF` / `EMPLOYEE_REF` — those would presuppose system tables |
| Cheque status | A *protected* `SELECT` column any Owner can add to any page, **not** a cheque state machine |
| Revenue balance check | An Owner-written `page_validations` rule in the Owner's own column names, **not** a hard-coded revenue variance check |
| CSV | One generic pipeline mapping any file to any page, **not** per-module importers |
| Dashboard | Widgets configured from the Owner's pages and columns, **not** fixed financial widgets |
| AI tools | `list_pages` / `get_page_schema` / `aggregate_records`, **not** `get_expenses()` / `get_pending_cheques()` |

## Consequences

**Positive**

- The product fits any shop, including ways of working this document has not imagined.
- Features are written once and work for every table forever. A new kind of business record costs
  the Owner five minutes and the developer nothing.
- The AI cannot be quietly hard-coded to one schema — which is verified by running the eval suite
  against **two fixture companies with completely different table names and structures**. Passing
  one and failing the other means something was hard-coded that should not have been.

**Negative / accepted costs**

- **The blank-page problem is the top product risk** (PROJECT_PLAN §28, risk 1). Flexibility is
  useless to an Owner who does not know what to build. Mitigated by a guided page builder with type
  hints, and a half-day onboarding session in P9 where the first four or five tables are built
  together from the existing spreadsheets.
- An Owner can design a structure that makes analysis hard — everything in one free-text Notes
  field. The builder nudges toward typed columns; the AI can say when a question is unanswerable
  because the data is unstructured.
- Nothing is optimised for a specific business shape, so some questions need an aggregation the
  Owner has to configure rather than a screen that already exists.

**V2 page templates** are the closest the product ever comes to shipping a pre-built table — and
even then, a template is a *starting point the Owner immediately edits*, created through the same
public page API, with no privileged code path.

## How this decision is defended

This is the decision most likely to be eroded under delivery pressure — "let's just add a small
revenue table for the dashboard". It is guarded by:

1. This ADR, plus PROJECT_PLAN §31 restating it as a non-negotiable.
2. Code review: any migration creating a business table is rejected.
3. The dual-fixture AI eval suite, which fails if the AI depends on specific table names.
