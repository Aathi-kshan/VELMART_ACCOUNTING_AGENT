# ADR 0001 — The page engine is the business data layer

- **Status:** Accepted — **amended by [ADR 0006](0006-prebuilt-business-tables.md)**
- **Date:** 2026-09-10
- **Deciders:** Owner, lead developer
- **Related:** [ADR 0006](0006-prebuilt-business-tables.md), [ADR 0002](0002-no-prebuilt-business-tables.md) (superseded), [PROJECT_PLAN §7](../PROJECT_PLAN.md), §10

> **Amendment (ADR 0006):** the page engine is no longer the *only* business data layer. Six
> tables — `employee_salaries`, `purchases`, `expenses`, `daily_revenue`, `cash_ledger`, `cheques` — are stored natively. They are still
> *described* by `pages` + `page_columns` (as system pages), so everything below about schema
> discovery, typing and the generic API still applies to them; only their storage differs. The
> single-source-of-truth rule is unchanged: a system page has **no** rows in `records`, and reserved
> keys prevent a duplicate page being created.

## Context

Earlier drafts framed the custom "page" engine as an *extension* sitting alongside seven hard-coded
financial tables (`daily_revenue`, `cash_ledger`, `expenses`, `salaries`, `cheques`,
`card_settlements`, `supplier_*`). That arrangement has a fatal property: if the Owner builds an
"Expenses" page *and* a hidden `expenses` table also exists, the same business fact can be written
to two places. Totals diverge, and the AI answers from whichever one it happened to be pointed at.

A second question had to be settled at the same time: how to store rows whose shape is defined at
runtime. The original proposal used EAV — one row per *cell* in a `record_values` table with
`value_text` / `value_number` / … columns.

## Decision

**The page engine is the only business data layer.** Business data lives in exactly three platform
tables:

- `pages` — the table the Owner named
- `page_columns` — the schema the Owner defined
- `records` — the rows, with values in a `data JSONB` column

There is no fourth place and no shadow financial table. Every business row exists once.

**Storage is JSONB, not EAV.** Values live in `records.data` with a GIN index, typed at write time
by a Pydantic model built at runtime from `page_columns`.

| | EAV | JSONB |
|---|---|---|
| Rows for 100k records × 12 columns | 1,200,000 | 100,000 |
| Read one page of 50 records | join + pivot 600 rows | 50 row reads |
| Filter on a field | self-join per predicate | `data->>'category' = 'X'` with an index |
| Aggregate | join + cast | `SUM((data->>'amount')::numeric)` |
| Type safety | none | enforced at write from `page_columns` |

**Typing is not lost.** JSONB is validated on every write against the Owner's column definitions.
Money is stored as a *string* in JSONB (`"35000.00"`) and parsed as `Decimal` — never as a JSON
number, which most parsers widen to a double.

**Hot columns get indexed projections.** Rather than one generated column per Owner column — which
would grow without bound — the platform maintains a fixed set of projection columns on `records`
(`num_1..num_4`, `date_1..date_2`), mapped per page via `pages.projection_map` for the columns the
Owner marks indexed.

## Consequences

**Positive**

- One source of truth per business record. Totals cannot disagree with themselves.
- Creating a business table requires no migration and no deploy — it is rows in `pages` and
  `page_columns`, written through the public API at runtime.
- Every feature written once serves every table the Owner will ever invent: one CSV pipeline, one
  set of record endpoints, one AI tool catalogue, one dynamic form renderer.
- Alembic manages only the platform schema, which stays small and stable.

**Negative / accepted costs**

- Filtering and aggregation must go through validated column keys mapped to safe expressions.
  Column keys are never interpolated into SQL (see [ADR 0002](0002-no-prebuilt-business-tables.md)
  consequences and PROJECT_PLAN §20.3).
- Only four numeric and two date projections exist per page. This covers every realistic page, but
  a page wanting a fifth indexed numeric column needs the projection budget revisited.
- The database cannot express a business-level `CHECK` across Owner columns. This originally said
  such rules were enforced by `page_validations` in the service layer; **that feature was removed**
  (migration `0014` drops the table), so cross-column rules are currently not enforced at all.
  Per-column constraints still are, through each column's own `config`.
- JSONB performance must be measured at ~100k records. One shop is years away from that volume.

## Invariants this ADR creates

1. `page_columns.key` is **immutable** after creation — changing it would orphan every value in
   every `records.data` blob.
2. No migration may ever create a business table. Migrations touch platform tables only.
3. Aggregation happens in Postgres over projection columns or `(data->>'x')::numeric` — never
   summed in Python across pages.
