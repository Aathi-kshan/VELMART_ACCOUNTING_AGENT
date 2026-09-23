# Velmart — full-system audit, remediation and verification

**Date:** 2026-09-20 · **Scope:** `apps/api` (FastAPI + PostgreSQL 18/RLS),
`apps/mobile` (Flutter + Riverpod), `infra/`, `docs/`

---

## 1. Executive summary

The brief was to audit, fix, re-test and report honestly — explicitly *not* to
stop because the existing test suite was green.

That instruction was the one that mattered. **The suite was green and the
system had confirmed data-integrity defects**, including one that silently lost
writes in an accounting application.

**60 defects were found and fixed**, each pinned by a test that fails without
the fix. Seven of those were introduced *by the remediation itself* and caught
by re-auditing it — recorded as such rather than quietly corrected. The last
two closed two of this report's own "would block a release" findings (R1, the
CI gate; R2, `mypy`'s coverage of `tests/`) after the initial 58-defect pass.

The five that mattered most:

1. **Optimistic locking did not work.** The version check compared in Python
   and the `UPDATE` carried no `version` predicate, on either storage path.
   Two people editing the same record both got `200`; the second silently
   overwrote the first. `FOR UPDATE` appeared nowhere in the codebase.
2. **The audit chain forked under concurrent writes**, ~1 run in 6, making the
   log report *itself* as tampered with. `id` is `BIGSERIAL`, assigned before
   the trigger takes its lock, so rows were chained in one order and verified
   in another. True since the chain was introduced.
3. **Floating-point arithmetic reached a money path.** `amount * 0.075`
   computed in `double precision` in Postgres while Python used `Decimal`, and
   that float fed `SUM()` and the running balance.
4. **There were no backups.** Both backup scripts were 0-byte files, nothing
   scheduled the nightly job, and the API image had no `pg_dump` at all — while
   the runbook documented 90-day retention and a 4-hour RTO that had never been
   measured.
5. **Idempotency keys were global, not per-tenant**, so one company could
   receive another company's stored response body.

**Release assessment: NOT READY** — see §6. The remaining blockers are
operational and small, not architectural.

---

## 2. Verification

All figures below were produced on this machine, on the final code.

| Check | Command | Result |
|---|---|---|
| Backend tests | `uv run pytest -q` | **724 passed**, 3 deselected (`slow`) |
| Backend lint | `uv run ruff check app/ alembic/ tests/` | **clean** |
| Backend types | `uv run mypy app/ alembic/ tests/` | **clean**, 221 files |
| Migration chain | `alembic heads` | **single head `0024`** |
| Migration round-trip | fresh DB → head → base → head | **clean**, 24 up / 24 down / 24 up |
| Flutter tests | `flutter test` | **150 passed** |
| Flutter lint | `dart analyze --fatal-infos` | **clean** |
| Flutter web build | `flutter build web` | **succeeds** |
| Volume benchmark | `pytest -m slow` at 100k rows | **passes**, all 5 measures inside target |
| Backup | `infra/scripts/backup_dump.sh` | **runs**, dump verified with `pg_restore --list` |
| Restore drill | `infra/scripts/restore_drill.sh` | **passes** — 29 tables, 458 rows, chain verified, 3s |
| Nightly job | `python -m app.tasks.nightly` | **all four tasks succeed** (`"failed": []`) |

Baseline before this work: 566 backend tests, 144 Flutter tests, all green,
lint and types clean, migrations at a single head. None of it caught anything
in §1.

### Volume benchmark, 100k rows per page

| Measure | Result | Target |
|---|---:|---:|
| generic page: filter + sort | 198 ms | 400 ms |
| generic page: aggregate over a FORMULA column | 78 ms | 400 ms |
| generic page: running balance | 347 ms | 400 ms |
| native page: filter + sort | 93 ms | 400 ms |
| native page: aggregate | 63 ms | 400 ms |

`running-balance` was historically recorded at **~690 ms** and over target;
bounding it brought it inside. The generic-page figures include a measured
38–62% cost from replacing an incorrect regex cast guard with real try-casts —
a trade-off taken deliberately and documented in `BUG_FIX_LOG.md` §53.

---

## 3. What the green suite was missing

Worth stating plainly, because it is the reusable lesson:

- **`test_optimistic_locking.py` had seven tests and not one used
  `asyncio.gather`.** Every case replayed a stale version *after* the first
  write committed, exercising only the Python-side comparison. The database had
  no guard at all.
- **Three test files were 0 bytes**, including one named for the AI-vs-human
  stale-version guard. Pytest reported success over them.
- **`test_manager_cannot_set_protected_field.py` made no database
  assertions** — the cheque-status guard could have been changed to "403 but
  write anyway" and all six tests would still pass.
- **The existing suite documented a bug as correct behaviour**:
  `test_direct_cycle_rejected_at_save_time` created a page whose formula
  referenced a nonexistent column and asserted `201`, because `POST /pages`
  never validated formula expressions at all.
- **CI's lint gate was already red** before this work started, including in a
  migration that predates it.

**Guards added so these cannot silently return:** real concurrency tests using
`asyncio.gather`; an evaluator-vs-SQL differential suite for the formula
engine; keyset pagination tests that walk the cursor to exhaustion and assert
every record appears exactly once; and `test_api_docs_match_routes.py`, which
parses `docs/API.md` and fails when it names an endpoint that does not exist —
that one immediately caught a documented endpoint that was never built.

---

## 4. Remaining issues

Nothing below is fixed. All of it is in `BUG_FIX_LOG.md` with detail.

### Would block a production release

| # | Issue |
|---|---|
| R1 | ~~CI was never updated~~ — **closed.** `.github/workflows/api-ci.yml` gained `uv lock --check`, `mypy app/ alembic/` (was `app/` only), and a new `migrations` job: a plain Postgres 18 service that asserts exactly one head then runs `upgrade head` → `downgrade base` → `upgrade head` on a genuinely fresh database. `mobile-ci.yml`'s dead "skip if no pubspec" guard is removed — `apps/mobile` has been a real app since P1, and the guard meant deleting `pubspec.yaml` would have reported green having run nothing. Both steps were exercised locally against a fresh container with the exact commands CI now runs before being wired in; see BUG_FIX_LOG.md #59. |
| R2 | ~~`mypy tests/` has 41 pre-existing errors~~ — **closed.** 39 errors across 15 files were fixed (mostly missing parameter/return annotations; a handful were real gaps — two `SELECT ... .one()` helpers untyped as `object` instead of SQLAlchemy `Row`, a `build_provenance` union return used without narrowing, a dynamically-built Pydantic class used as a type-subscript variable mypy can't resolve). One config fix went with them: `mypy tests/` in isolation raised "source file found twice under different module names" — `tests/ai/test_golden_questions.py` imports a sibling by its fully-qualified `tests.ai.` path, and with no `__init__.py` anywhere in `tests/`, that import path and the directory-walk path disagreed on the file's module name. Fixed with `mypy_path`/`explicit_package_bases` in `pyproject.toml`, not a CLI flag, so a developer running plain `mypy tests/` gets the same clean result CI does. `mypy app/ alembic/ tests/` now covers all 221 source files with zero errors, and CI runs exactly that. |
| R3 | **Backups are local-only.** There is no storage layer, so the dump lands on a mounted volume and is never shipped off-platform. The RUNBOOK's "off-platform copy" line is now marked not-implemented rather than claimed. |
| R4 | **The restore drill's 3s is not the RTO.** It was measured against a 458-row development database. Re-run against production-sized data before treating the 4-hour RTO as evidenced. |

### Correctness, found but not fixed

| # | Issue |
|---|---|
| R5 | **FORMULA sort cursors are unreliable.** Non-numeric formula results (a date, a boolean) raise on `_coerce` and 422 the second page; and Python `Decimal` (28 digits) vs Postgres `NUMERIC` (~16–18) can disagree on the cursor value, skipping or duplicating a boundary row. |
| R6 | **Projection-slot keyset mismatch.** `resolve_column` sorts on `Record.num_1`/`date_1` while `_row_value` reads the raw JSONB, so an indexed NUMBER rounded to the slot's scale, or an indexed DATETIME truncated to a date, can drop rows at a page boundary. |
| R7 | **`aggregate.record_count` no longer matches the list it labels** — aggregates exclude non-ACTIVE rows (correctly) while `query_records` and the CSV export include them. |
| R8 | **MULTI_SELECT search matches JSON punctuation**, because a generic page searches the array's raw text. No native table has such a column, so the "same on both backends" claim is untested rather than true. |
| R9 | **Users, stores and page-access grants have no version column**, so concurrent edits to them remain last-write-wins. `pages` and `records` are covered. |
| R10 | **`DELETE /records/{id}` ignores a client `If-Match`.** It is guarded by the version it just read, so it cannot lose a write, but a caller cannot say "only if unchanged". |
| R11 | **AI cost accounting is still lost on a failed pipeline** (the rate limit is now durable); two DB transactions stay open across OpenRouter calls; a zero-item proposal can be marked APPLIED. |
| R12 | **The audit chain is now globally serialised.** Every audited mutation takes the single head row's lock for the remainder of its transaction. Correct, and the price of a chain that does not fork — but it is a throughput ceiling worth knowing about. |

---

## 5. Blocked by environment

Not tested, and **not** reported as passing.

| Item | Status | Evidence |
|---|---|---|
| **macOS build** | `BLOCKED — ENVIRONMENT` | `xcodebuild -resolvePackageDependencies` hangs at 0% CPU with no child processes, with Flutter out of the picture entirely. `swift package resolve` on a freshly-created package **with no dependencies** also produces nothing. Xcode 26.6, license accepted, `xcode-select` correct. SwiftPM stalls here independently of Velmart. My earlier hypothesis — that `sqlite3_flutter_libs` in the plugin graph caused it — was **wrong**; removing it changed nothing. |
| **iOS / Android** | `BLOCKED — ENVIRONMENT` | No simulator or Android SDK configured. |
| **Railway deployment** | `BLOCKED — ENVIRONMENT` | No credentials. `infra/railway.cron.json` is written and the job runs locally, but the deployed cron is unverified. |
| **Sentry** | `BLOCKED — ENVIRONMENT` | No DSN; wiring reviewed statically only. |
| **Live AI / OpenRouter** | `BLOCKED — ENVIRONMENT` | The configured key was already known non-working. AI verification is at the orchestrator/tool-contract level. |

---

## 6. Release assessment

### **NOT READY**

Not because of the code — the data-integrity and tenancy defects that made the
system genuinely unsafe are fixed and proven by tests that fail without them.
It is not ready because the things that catch the *next* defect are not in
place:

1. ~~CI does not gate what now matters~~ — **closed** (R1). The migration
   round-trip, single-head check, and `uv lock --check` are now enforced on
   every push, and `mypy` covers `app/`, `alembic/` and `tests/` together (R2).
2. **Backups exist but never leave the machine** (R3). A verified local dump is
   most of the work and none of the insurance.
3. **The RTO is still unevidenced** (R4).
4. **The client cannot be built for its target platform here** (§5), so no
   end-to-end verification on a real device has been possible.

R3 needs the storage layer; R4 needs one run against realistic data. With
those closed and a device build verified somewhere with a working Xcode, the
assessment becomes READY.

**What I would not ship without:** R3 and R4 — the two operational blockers
that remain. Everything found in this audit was found
by something that fails loudly. The gaps that remain are the places where
nothing does.
