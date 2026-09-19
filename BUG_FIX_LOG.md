# Bug fix log

Defects found during the full-system audit, with the test that fails without
the fix. Entries are grouped by the round that found them.

Baseline before any of this work: **566 backend tests passing**, 144 Flutter
tests passing, `dart analyze --fatal-infos` clean, `mypy` clean, migrations at
a single head. None of that caught anything below.

Severity: **P0** = silent data loss, wrong money, or a tenancy boundary.
**P1** = wrong behaviour, an avoidable 500, or a missing guard.

---

## Round 1

### 1. Optimistic locking did not prevent lost updates — P0

**Symptom.** Two people editing the same record both got 200. The second
write silently replaced the first, with no conflict reported to anyone.

**Root cause.** The version check was check-then-act.
`record_service._check_version` compared `handle.version` to the caller's
version *in Python*, and `repositories/records.update_row` then issued
`UPDATE ... WHERE id = :id` with **no version predicate**, on both the native
and JSONB branches. `with_for_update` appears nowhere in `app/`, and the
engine runs at READ COMMITTED (`app/db/session.py`). Two callers could both
read version 3, both pass the check, and both write version 4.

**Why the suite missed it.** All seven tests in
`tests/test_optimistic_locking.py` replay a stale version *after* the first
write has committed, which only exercises the Python comparison. Not one used
`asyncio.gather`.

**Fix.** `repositories/records._guarded_update` puts `version` in the WHERE
clause and uses `RETURNING id` to detect a miss, raising `VersionConflictError`
with the row's current version. Routed through `update_row`, `soft_delete_row`
and `mark_reversed`, so the protected-field and proposal-apply paths inherit it.

**Proving test.** `tests/test_concurrency_races.py::
TestLostUpdateIsBlockedByTheDatabase::
test_a_writer_holding_a_stale_handle_cannot_overwrite_the_winner` — two
sessions read version 1, then write in sequence. Fails with `DID NOT RAISE`
before the fix.

**Note on the HTTP-level tests.** Measured against the unfixed code, six
concurrent `PATCH`es already produced 1×200 and 5×409, because a request holds
its transaction — and the audit chain's global tail lock — for its whole
duration, serialising them. Those tests are kept as protocol regression guards
and are explicitly documented as *not* detectors.

### 2. `soft_delete_row` never bumped `version` — P0

**Symptom.** A delete was invisible to optimistic locking: a caller holding a
handle from before the delete could still update the row.

**Fix.** The delete bumps `version` and goes through `_guarded_update`.

**Proving test.** `test_a_stale_soft_delete_cannot_erase_a_committed_update`.

### 3. A business column could overwrite platform fields — P0

**Root cause.** On the native path `update_row` built `values` with
`version`/`occurred_at`/`business_date`/`updated_by` and then ran
`values.update(validated)` — business data last, so a column keyed like a
platform field would overwrite the lock increment.

**Fix.** Business columns are spread first, platform fields last.

### 4. One refresh token could mint several live families — P0

**Symptom.** Six concurrent `POST /auth/refresh` with the same token returned
**six** 200s.

**Root cause.** `auth_service.refresh` read `revoked_at`, did its work, and
revoked the row at the end, with no lock. Worse than duplicate sessions: each
request marked the row revoked *itself*, so a genuinely stolen token never
tripped the reuse detector.

**Fix.** Claim the token first with
`UPDATE ... WHERE id = :id AND revoked_at IS NULL RETURNING id`. The loser
fails closed without revoking the family — a client retrying after a network
flake is indistinguishable from an attacker in that instant, and a later
replay still hits the reuse path.

**Proving test.** `TestConcurrentRefreshRotation::
test_one_refresh_token_yields_one_new_family`.

### 5. Floating-point arithmetic on a money path — P0

**Symptom.** `amount * 0.075` was computed in `double precision` in Postgres
while Python used `Decimal`, and that float flowed into `SUM()` and into the
running balance.

**Root cause.** `sql_compiler._compile_node` returned `node.value` unconverted
for `ast.Constant`, so a float literal bound as `float8`. The Python evaluator
was already correct (`evaluator._coerce_constant`).

**Fix.** Float literals bind as `NUMERIC`. Integer literals deliberately stay
integers — Postgres `numeric op integer` is exact, and `round(x, 2)` requires
a genuine integer second argument.

**Proving test.** `tests/test_formula_backend_parity.py::TestNumericParity`.

### 6. Reversed records were still counted in totals — P0

**Symptom.** After any reversal a ledger page's `sum` and the last row of its
running balance disagreed, with nothing to say which was right.

**Root cause.** `running_balance` filtered `status == ACTIVE`; `aggregate` and
`column_values` started from `base_conditions`, which scopes by page and
`is_deleted` only. A reversal keeps the original row *and* writes a correcting
one, so the reversed amount was counted twice.

**Fix.** New `repositories/records.active_conditions`, used by `aggregate` and
`column_values`. `query_records` deliberately still lists non-ACTIVE rows so a
reversed record stays visible with its status.

**Proving test.** `tests/test_totals_exclude_non_active.py::
test_sum_and_running_balance_agree_after_a_reversal`.

### 7. A row count was formatted as money — P1

`count` of a CURRENCY column reported `"4.00"` for 4 rows, because
`metric_column` described the input rather than the result.

**Proving test.** `TestCountIsNotFormattedAsMoney`.

### 8. The two formula backends disagreed — P1

Same expression, different answers depending on whether it was read on a
record or aggregated in SQL:

- **Integer division.** `days_between(a, b) / 2` → `2` in SQL (integer
  division), `2.5` in Python. Fixed by forcing NUMERIC on division and on
  `days_between`'s result.
- **NULL semantics.** Postgres `least()`/`greatest()` *skip* NULLs; the Python
  evaluator propagates them. Aligned on propagation — a total that treats "not
  entered yet" as "not a candidate" is wrong in a way nobody notices.
- **Timezone.** `today()` hardcoded `Asia/Colombo` in SQL but read
  `COMPANY_TIMEZONE` in Python. Now shares the constant.

**Why the suite missed it.** The only cross-backend test used a single
addition on clean non-null data.

**Proving tests.** `tests/test_formula_backend_parity.py` (36 cases).

### 9. Formula calls had no arity validation — P1

`sum()` raised `IndexError` in the SQL compiler and returned `Decimal(0)` in
Python; `coalesce()` compiled to `COALESCE()`, a Postgres syntax error;
`abs(a, b)` raised `TypeError` in Python and was silently truncated in SQL. An
uncaught `IndexError` inside a filter or aggregate is a 500.

**Fix.** `functions.FORMULA_ARITY` as the shared contract, enforced in the
parser at save time → 422.

### 10. `POST /pages` never validated FORMULA expressions — P1 (new)

**Found by writing the arity tests**, not by the audit sweeps.
`formula_service.validate_formula_column` was only called from
`schema_service.add_column`/`update_column`, so an expression supplied in the
initial page payload skipped the whitelist parser entirely. It then failed
silently on read (`formula_service.prepare` swallows the parse error and the
column renders blank forever) or as a 500 from the SQL compiler.

The existing suite *documented* the bug: `test_direct_cycle_rejected_at_save_time`
created a page whose formula referenced a nonexistent column and asserted 201.
Its setup was rebuilt to introduce the cycle through `PATCH /columns/{id}`;
the assertion is unchanged.

**Proving tests.** `TestCreatePageValidatesFormulas`.

### 11. Idempotency keys were global, not per tenant — P0

**Symptom.** `idempotency_keys.key` was the sole primary key and `lookup`
filtered on `WHERE key = :key` alone. A key string is client-supplied, so one
company presenting a key another had used on the same endpoint with a
hash-equal body received **that company's stored response body**. The same
global namespace also let one tenant's key block another's request with a 409.

`idempotency_keys` is deliberately RLS-exempt, so nothing below the
application constrained it.

**Fix.** Migration `0017` backfills `company_id` from each row's owning user
and makes the primary key `(company_id, key)`; `lookup`/`reserve`/
`store_response` all scope by company.

**Proving tests.** `tests/test_idempotency.py::TestKeysAreScopedPerCompany`.

### 12. `store_id` in a request body was never validated — P0

**Symptom.** An Owner could persist a record whose `store_id` pointed at
**another company's** store. RLS `store_scope` short-circuits for OWNER and
`tenant_isolation` constrains only `company_id`. A STORE_REF *column* was
always checked; the loose body field was not.

**Fix.** `record_service._resolve_store_id` applies the same company check
STORE_REF columns get, plus the manager's own store assignment, on create
*and* update. It also re-derives `store_id` on update, fixing a second bug
where editing the page's store column left `records.store_id` stale — so a
manager's RLS scoping kept matching on the old store.

**Proving tests.** `tests/test_store_scoping.py::TestRecordStoreId`.

### 13. `store_ids` in user management was never validated — P1

An Owner could assign one of their managers to another company's store.
`user_stores` has no `company_id` and is RLS-exempt, and those ids become the
manager's RLS store scope via `auth_service.store_ids_for`.

**Proving tests.** `TestUserStoreAssignments`.

### 14. Sorting by a column with missing values lost records — P0

Two separate faults, both silent:

- **Unreachable rows.** The keyset predicate was a bare `expr > value`.
  `NULL > anything` is NULL, never true, so on an ascending sort the empty
  rows were ordered into a block at the end that no page could ever reach.
- **Corrupted cursor.** `_encode_scalar(None)` produced the *string* `"None"`,
  which `parse_cursor` then tried to read back as a date/Decimal/UUID. A page
  ending on a row with an empty sort value made the next page return
  "Invalid or corrupted cursor".

**Fix.** Explicit `NULLS LAST` in both directions (Postgres otherwise defaults
NULLs first on DESC and last on ASC, so the same data disagreed with itself);
a null-aware cursor carrying real JSON `null`; and a null-aware keyset
predicate. Nothing is "past" a NULL under NULLS LAST, so progress out of the
trailing block comes from the id tiebreaker — returning `IS NULL` there
instead re-matched the cursor's own rows and paged forever, which the tests
caught.

**Proving tests.** `tests/test_pagination_with_nulls.py` — each walks the
cursor to exhaustion and asserts every record is returned exactly once.

### 15. CI was already failing before this work — P1 (new)

`ruff check app/ alembic/ tests/` is what CI runs, but only `app/` had been
being checked locally. Six line-length violations in `tests/` and two import
ordering errors in `alembic/` — including one in a migration predating this
session — meant the lint gate was red. Fixed.

### 16. `base_conditions` did not scope generic pages by company — P1

Defence in depth: a generic page's rows were scoped by `page_id` alone,
correct only because the `Page` was already company-scoped and RLS sits
behind it. Now asserted explicitly.

---

## Round 2 — Stage 3 (correctness, availability, integrity)

### 17. `contains` on a non-text column was a 500 — P1

`_apply_filter` built `expr.ilike(...)`, but `resolve_column` types the
expression as NUMERIC/DATE/BOOLEAN for those column kinds. Postgres has no
`numeric ~~* unknown` operator, so filtering "contains" on an amount reached
the client as an unhandled `ProgrammingError`. Now a 422, since substring
matching on a number has no meaning.

**Proving test.** `tests/test_query_does_not_500.py::TestContainsOnANonTextColumn`.

### 18. Narrowing a column's type bricked the page — P1

**Symptom.** After changing a TEXT column to NUMBER, the page could no longer
be listed, filtered, sorted or totalled. Every request 500'd, and there was
no way back through the API because *reading* it is what failed.

**Root cause.** A generic page casts `data ->> key` to NUMERIC on every row,
and one unconvertible value fails the whole statement. This is reachable
through the documented workflow, not just corrupt data:
`POST /columns/{id}/narrow-dry-run` is explicitly informational and "never
mutates or deletes anything", and `PATCH /columns/{id}` with
`confirm_narrow=true` then changes the declared type **without converting or
removing the rows the dry run just warned about**. An Owner who accepts the
warning bricks the page.

**Fix.** `_guarded_cast` in `repositories/records.py` casts only when the
stored text matches the shape of the target type, yielding NULL otherwise —
the same way an unevaluatable formula already reads as blank, and (with the
NULLS LAST ordering from Round 1) sorting to the end rather than vanishing.

**Proving tests.** `TestAColumnNarrowedOverIncompatibleData` — list, sort,
filter and total, all driven through the public API.

### 19. "Search" meant two different things — P1

On a generic page it matched `cast(Record.data, Text)`: the **whole JSONB
blob, including the key names**. Searching "amount" matched every row that
merely had an amount column, and searches also hit raw UUIDs and stored
dates. On a system page it matched only TEXT/LONG_TEXT columns — and a system
page with no text column compiled to `where(false())`, so it could never
return a row whatever was typed.

Both now search the page's text-valued columns.

**Proving tests.** `TestSearchMeansTheSameThingOnBothBackends`.

### 20. A permission denial committed the caller's work — P1

`guards.py` made its denial audit durable by calling `session.commit()` on the
**caller's** session. That committed whatever else the request had already
written — turning a refusal into a partial save — and ended the transaction
`get_rls_session` was still holding open, discarding the transaction-scoped
RLS settings with it.

**Fix.** `_audit_denial` writes on its own short-lived session. The audit is
durable; the request's transaction rolls back exactly as a failed request
should.

### 21. Writing an audit row silently broke RLS scoping — P1

`write_audit_log` called `set_rls_context` on every write. That helper
rewrites **all three** settings, and the audit call passed no `store_ids` — so
every audit write inside a request cleared the store scope for every query
that followed it. It also defaulted to `role="OWNER"` when `actor_role` was
omitted, quietly raising the transaction's RLS role.

Audit writes are never the first thing a request does, so the caller has
already armed the context; `audit_logs` carries `tenant_isolation` only, so
the arming was never needed for the insert itself.

**Proving tests.** `tests/test_audit_write_preserves_rls_context.py`, which
reads the settings back out of Postgres — the only place the damage was
visible.

### 22. The login rate limiter put the whole deployment in one bucket — P1

`_client_ip` read `request.client.host` and nothing else. Behind a
terminating proxy (Railway's deployed shape) every request arrives from the
proxy, so five failed logins from anyone locked out **every** user, and the
per-attacker limit did not exist.

Fixed with an opt-in `TRUSTED_PROXY_HOPS` setting, default 0.
`X-Forwarded-For` is client-supplied, so honouring it unconditionally would be
worse than ignoring it — a caller could forge a fresh IP per request and never
be limited at all.

**Proving tests.** `tests/test_rate_limit_wiring.py::TestLoginIpResolution`,
including that a forged header cannot buy a fresh bucket when no proxy is
configured.

### 23. The per-user API throttle did not exist — P1

`RATE_LIMIT_PER_MINUTE` was configured and `ratelimit.hit_api_user` was
written and working, with **zero call sites**. Now applied in
`dependencies/auth._authenticate`, the one place every authenticated request
already passes through, riding the transaction it was opening anyway.

### 24. The AI tool-schema safety gate only checked the top level — P1

`_require_no_leaked_context_fields` inspected the root `properties` only.
Pydantic hoists nested models into `$defs`, so a field on a nested model never
appears at the root — and real tools already nest (`QueryRecordsParams`
carries `QueryFilter` and `SortSpec`). A `company_id` added to one of those
would have passed the gate silently, which defeats the point of a build-time
guarantee. Now checked at every depth, with `$ref` cycle protection.

### 25. The audit hash chain did not cover six of its own fields — P1

It hashed ten fields and omitted `page_id`, `actor_role`, `diff`,
`ai_session_id`, `ip_address` and `user_agent`. `page_id` is load-bearing —
`audit_read_service` filters page history on it and a manager's audit
visibility is decided by it — so anyone able to UPDATE the table could
re-point an entry at a different page, or change who appeared to have acted,
and the chain still verified clean.

Migration `0018` covers every audited field, re-hashes existing rows in `id`
order so history stays continuous, and updates the verifier to match.

**Proving tests.** `TestEveryAuditedFieldIsTamperEvident` — six cases, each
altering one previously-unhashed column and requiring the verifier to name
that exact row.

### 26. The chain's "serialisation" did not serialise — P1

0005's trigger took `SELECT ... ORDER BY id DESC LIMIT 1 FOR UPDATE` and its
comment claimed that stopped concurrent inserts sharing a `prev_hash`. Under
READ COMMITTED it does not: T2's snapshot predates T1's commit, so after
waiting, T2's EvalPlanQual recheck re-evaluates only the row it locked and
returns the same hash. Two rows then carry the same `prev_hash` and the chain
forks — which the verifier reports as tampering. The failure mode was a false
tamper alarm under ordinary concurrent load.

Replaced with `pg_advisory_xact_lock` on a fixed key.

**Proving test.** `TestConcurrentAuditWritesDoNotForkTheChain`.

### 27. `running_balance` was unbounded — P1

The one endpoint with no limit: it returned every active ledger row in a
single response, which is also why it was the only endpoint to miss its
latency target at volume. Now returns the most recent `limit` entries. The
window function still accumulates over the page's whole history, so the
balances shown are the real ones; only how far back the listing reaches is
bounded.

### 28. A test-infrastructure trap, fixed at the root — P1 (new)

Clearing the app's cached engines happened inside the `client` fixture, so it
covered tests that go through HTTP and nothing else. Any test calling app code
that reaches `get_sessionmaker()` directly — such as a guard writing its
denial audit on its own connection — got a connection pooled on a previous
test's event loop and failed with "attached to a different loop". Promoted to
an autouse fixture so the trap is gone rather than waiting to be rediscovered.

---

## Round 3 — closing the Stage 3 deferrals

### 29. `pages.version` existed, was published, and never moved — P1

**Symptom.** A page's `version` stayed at 1 for its entire life, however many
times it was renamed or its columns added, retyped or archived.

**Why it matters twice over.** A client caching a `PageSchema` had no way to
tell it had gone stale — which matters precisely because this engine's promise
is that an Owner changes a page's columns and clients pick the change up with
no app release. And publishing a `version` on every `PageOut`/`PageSchemaOut`
implied an optimistic-locking check that did not exist: `If-Match: 1` was
accepted forever, so two Owners restructuring a page at once silently
overwrote each other.

**Fix.** `page_service.bump_schema_version` advances the version on page
updates and on every column add/edit/archive (archive routes through
`update_column`, so all three are covered). `PATCH /pages/{id}` now honours
`If-Match` — **optionally**, because the Flutter client sends that header for
records only (`page_repository.dart`), and requiring it would have broken
every existing caller.

**Proving tests.** `tests/test_page_schema_version.py` — 11 cases; 7 failed
before the fix, including `If-Match: 1` being accepted twice in a row.

### 30. A failing AI request was free and unthrottled — P1

`ratelimit.hit_ai_user` ran inside the request's single transaction, and
`run_pipeline` catches only `OpenRouterError` — so any other failure rolled
the transaction back and took the rate-limit increment with it. A request
that failed reliably could be repeated without limit against a paid API.

**Fix.** `_meter_ai_request` counts the request on its own connection and
commits immediately, the same pattern as the denial audit. (`rate_limits` is
non-tenant with no RLS policy, so the fresh session needs no context armed.)

### 31. `column_values` bypassed the wire-format converter — P1

It returned `str(v)` instead of `to_wire_value`. Those values feed a filter
picker and are sent straight back as filter values, so the two storage
backends could disagree about the same amount — a native page's
`NUMERIC(14,2)` stringified as `"3500.00"` while a generic page's JSONB text
came back however it was stored, and a picker built from one backend offered a
value that never matched on the other.

### 32. Truncating the audit log was undetectable — P1

The hash chain proves no row *between* two others was altered, because each
row's hash feeds the next. It proved nothing about the end: delete the newest
*k* rows and what remains still links up and verifies clean. Deleting recent
entries is also the obvious way to cover a trail, so the one thing the chain
could not see was the most likely thing to happen to it.

**Fix.** Migration `0019` adds `audit_chain_anchor`, recording where the chain
reached at the last clean verification. `app_user` and `ai_reader` are granted
**nothing** on it — an attacker holding the application's own database role
cannot re-anchor to match a truncation they just made, which is the point of
keeping it outside `audit_logs`.

**Proving tests.** `TestTailTruncationIsDetected` — including that the
surviving rows are individually intact (`first_broken_id is None`), which is
exactly why the row-by-row check alone could never catch this, and that the
app role cannot read the anchor at all.

---

## Round 4 — Stage 4 (operational reality)

### 33. The audit chain forked under concurrent writes — P0

**The most serious defect found in this round, and it was found by refusing to
call a flaky test flaky.**

**Symptom.** Eight parallel record creates left the chain reporting itself
tampered with, roughly **one run in six**. Every request succeeded; the
verifier then named a row as broken.

**Root cause, in two layers.** The first was the locking, fixed in 0018 and
0020: 0005 locked the log's current *tail row*, which does not stop another
transaction inserting a new row, and an advisory lock alone still let a
BEFORE-INSERT trigger read a stale predecessor, because such a trigger's
`SELECT` runs under the snapshot of the statement that fired it. 0020 moved
the contention onto a single `audit_chain_head` row, where a blocked writer
re-reads the newest committed version once the holder commits.

That reduced the failures but did not remove them, because the real problem
was **ordering**. `audit_logs.id` is `BIGSERIAL`, and Postgres evaluates the
column default *before* BEFORE-INSERT triggers run — so the id is fixed before
the trigger acquires the chain lock. Two concurrent inserts can take their ids
in one order and the lock in the other:

    T1 takes id 5, T2 takes id 6
    T2 wins the lock  ->  prev_hash(T2) = hash(row 4)
    T1 acquires next  ->  prev_hash(T1) = hash(T2)

The chain is perfectly well formed in *lock* order (4 -> T2 -> T1), but
`audit_chain_verify` walked it `ORDER BY id` (4 -> T1 -> T2), where T1's
`prev_hash` matches nothing. So two records written at the same instant made
the audit log declare itself tampered with — in the one subsystem whose entire
value is being trustworthy about that.

This has been true since the chain was introduced in 0005. It only became
visible once a test wrote to it concurrently.

**Fix.** Migration `0021` adds `chain_seq`, allocated inside the trigger while
the head row is held, and the verifier and restore drill walk that instead of
`id`. "The order rows were chained in" and "the order rows are verified in"
are now the same thing by construction.

**Proving test.** `TestConcurrentAuditWritesDoNotForkTheChain` — previously
failing 2 of 12 runs, now 25 of 25 across two batches.

### 34. A missing chain head row broke every audit write — P0 (self-inflicted, caught before commit)

The first version of `0021` assumed `audit_chain_head` always had its row. The
test suite truncates every table between tests, so the row vanished and
`NULL + 1` produced a NULL `chain_seq` — **407 tests failed**. Since every
mutation writes an audit row, this would equally have broken the entire
application in production had anything ever emptied that table (a TRUNCATE, a
partial restore). The trigger now recreates the head row if it is missing,
under the lock it already holds.

### 35. The API image had no `pg_dump` — P1

`infra/Dockerfile.api` never installed `postgresql-client`, and
`python:3.13-slim` does not ship one. `app/tasks/export_build.py` shells out to
`pg_dump`, and its docstring claimed the binary was resolved "via PATH (as the
Docker image provides it)" — which was untrue, so the nightly backup could only
ever have failed with "pg_dump not found".

Installing Debian's package was not enough either: it is `pg_dump` 17 against a
Postgres 18 server, and pg_dump refuses to dump a server newer than itself. The
image now installs `postgresql-client-18` from the PostgreSQL project's own apt
repository.

### 36. The backup failure said nothing about why it failed — P1

`export_build` ran `pg_dump` with `check=True, capture_output=True`, so the
raised `CalledProcessError` carried only the argv and an exit status while the
one line that identified the problem — `server version 18.6; pg_dump version
17.11` — was discarded. That is how a simple version mismatch reached the
nightly log as an unexplained non-zero exit. The failure now carries
`pg_dump`'s own message.

### 37. The backup was written somewhere it could not survive — P1

`export_build` wrote into `tempfile.gettempdir()`, which on a container
platform is discarded on the next redeploy. Even once scheduled, it would have
produced no retained backup at all — while reporting success. `BACKUP_DIR` now
directs it at a mounted volume, and the result carries `persistent`, with a
`backup.not_persistent` warning when it is unset, so "the backup succeeded"
cannot be read as "a backup exists".

### 38. Nothing scheduled the nightly job — P1

`app/tasks/nightly.py` orchestrates chain verification, backup, idempotency
cleanup and digests, and exits non-zero on failure. Nothing ran it:
`infra/railway.json` defines the API service only and carries no cron block,
and no workflow invoked it — while `docs/RUNBOOK.md` described a "Railway cron"
at 02:00 SLT. So the chain was never verified, no backup was ever taken, and no
digest was ever produced.

Added `infra/railway.cron.json` (a separate Railway cron service, scheduled
`30 20 * * *` = 02:00 Asia/Colombo) and a `nightly` profile in
`docker-compose.yml` so the job can be exercised locally instead of only
running unattended.

**Verified by running it**, which had never happened: all four jobs now report
success — chain verified across 213 rows, a 144 KB dump written to the mounted
volume, idempotency keys purged, digests for both companies.

### 39. There were no backups, and no restore had ever been attempted — P0

`infra/scripts/backup_dump.sh` and `restore_drill.sh` were **0-byte files**,
while `docs/RUNBOOK.md` described them as the mechanism behind 90-day retention
and carried a "Restore drill log" table it called "the evidence that the RTO is
real" — empty, with a 4-hour RTO that had never been measured.

Both are now implemented and, more importantly, **run**. The backup verifies its
own dump with `pg_restore --list` before keeping it and writes a checksum
beside it; the drill restores into a throwaway database, compares the migration
head, compares every table's row count, and re-verifies the audit chain inside
the restored copy.

First drill ever performed: **29 tables, 458 rows, head 0021, chain verified,
3 seconds.** Recorded in the RUNBOOK — along with the caveat that a 458-row
development database does not evidence a 4-hour RTO at production volume.

### 40. Personal data leaked past the log scrubber — P1

`_scrub` walked only the event dict's own keys, so anything nested passed
through: `{"record": {"data": {...}}}` logged every business value the `data`
entry exists to redact. The key list also omitted `email`, `phone`, `nic`
(Sri Lankan national identity card), `cookie`, and the `old_data`/`new_data`/
`diff` audit payloads. Now recursive, depth-bounded, and considerably wider.

### 41. Building the image would have produced a broken container — P1

There was no `.dockerignore` anywhere. `infra/Dockerfile.api` does
`COPY --from=builder /app/.venv /app/.venv` and then `COPY apps/api/ .`, so the
second copy pulled in the developer's local `apps/api/.venv` — not merely
bloating the image, but **overwriting the virtualenv built in the builder
stage** with one compiled for the developer's platform. A macOS arm64 venv
landing on a linux image yields a container that cannot start.

Also removed the 0-byte `apps/api/Dockerfile` sitting beside the real one, and
added a `HEALTHCHECK`.

### 42. A company could exist with no pages and no way to fix it — P1

See the correction below for what was originally claimed. `seed_demo.py` could
only create one hardcoded demo company, so onboarding a real second company
meant editing the source, and a company that already existed without system
pages could not be repaired at all. The live database held exactly that:
`Kandy Test Traders` with **zero pages**.

It now takes `--name`/`--owner-email`/`--password`, keeps `--demo` for the old
behaviour, and adds `--repair-all`, which gives every existing company any
system pages it is missing. Both paths are idempotent.

**Run against the live database**: `Kandy Test Traders` went 0 -> 6 pages
(including the correctly renamed "Purchases for Cash"), and the already-complete
company was left untouched.

---

## Round 5 — Stage 5 (scope hygiene and the two product decisions)

### 43. Ledger corrections were impossible from the app — P1

`POST /records/{id}/reverse` has existed since P4, and the client already
rendered the resulting `REVERSED` status — but nothing could ever *trigger* a
reversal. A `kind=LEDGER` page also rejects `PATCH` outright on the server, so
reversal is not one way to correct a ledger entry, it is the only way. The
result was a ledger nobody could correct.

Added an Owner-only "Reverse this entry" action on record detail, shown only
for a LEDGER page and only on an ACTIVE record, passing the record's `version`
as the optimistic-locking check. The confirm copy says what reversal actually
does — the entry stays visible, marked reversed, and stops counting towards
totals — because a ledger that quietly loses rows is worse than one that shows
its corrections.

**Proving tests.** `test/features/pages/presentation/record_reversal_test.dart`
— 6 cases including that a REGISTER page, a Manager, and an already-reversed
entry are each offered nothing.

### 44. The dashboard-widget feature was removed — product decision

Nothing in the codebase could create a widget: no create endpoint, no other
insert path. `docs/API.md` conceded it in passing — "nothing in the app creates
a new one" — so the table could only ever be empty in production and all four
endpoints could only ever return nothing. The tests concealed this by seeding
rows with raw SQL, commented there as "the only way to get a widget".

Removed on the product owner's decision rather than completed: finishing it
meant designing and securing a feature nobody had asked to finish, where
removing it drops ~400 lines plus four endpoints that still had to be
permission-checked, audited and maintained. Migration `0022` drops the table.
`GET /reconciliation` and `GET /dashboard/digest` are unrelated and stay.

### 45. Three dead Flutter dependencies, one of them in every native build — P2

`drift` and `sqlite3_flutter_libs` were declared for an offline cache cut from
scope, and `fl_chart` for the dashboard charts just removed. None was imported
anywhere in `lib/` or `test/`. `sqlite3_flutter_libs` is a **native** plugin,
so despite being unused it was still compiled into the generated macOS/iOS
SwiftPM package and pulled into every native build. All three removed (seven
transitive packages).

**This did not fix the macOS build** — see below. It was still worth doing;
the hypothesis was simply wrong.

### 46. ATTACHMENT was offered as a column type and could never work — P1

The column-type dropdown listed every `ColumnType` value, ATTACHMENT included.
Choosing it produced a column rendering "Uploading attachments is coming soon"
permanently: the attachment endpoints are deferred and
`app/routers/attachments.py` is not mounted. Offering a choice that cannot work
is worse than not offering it. The value stays in the enum so any column
already carrying it still parses and displays; it is simply no longer
selectable for a new column.

### 47. Dead stubs removed — P2

`app/core/pagination.py` (pagination lives in `query_service`),
`app/repositories/pages.py`, `app/services/export_service.py` (export lives in
`csv_service`/`routers/exports.py`), the Flutter `core/sync/*` and
`core/storage/database.dart` (removed offline scope), and
`tests/test_offline_sync_idempotency.py` — all 0 bytes and unreferenced.

Also removed the two empty `integration_test/*.dart` files and the two empty
`tests/ai/test_proposal_*.py` placeholders. The attachment stubs are kept: they
are documented deferred scope rather than accidental residue.

---

## macOS build — BLOCKED, ENVIRONMENT

Recorded here because an earlier round asserted a cause that turned out to be
wrong.

**The hypothesis was that `sqlite3_flutter_libs` in the generated SwiftPM
package caused `flutter run -d macos` to hang. It did not.** With all three
dead dependencies removed and the package graph down to `share_plus` and
`FlutterFramework`, `flutter build macos --debug` still stalled at
`xcodebuild -resolvePackageDependencies` — 11 minutes at 0% CPU with no child
processes, producing no output at all.

Isolated further, with Flutter removed from the picture entirely:

* `xcodebuild -resolvePackageDependencies` invoked directly on
  `macos/Runner.xcodeproj` hangs the same way, printing only its invocation
  banner.
* `swift package resolve` on a freshly created local package **with no
  dependencies whatsoever** also produces nothing.

Toolchain state is otherwise healthy: Xcode 26.6 (17F113), `xcode-select` at
`/Applications/Xcode.app/Contents/Developer`, first-launch status clean.

So SwiftPM itself stalls in this environment, independently of Velmart. The
macOS build is therefore **BLOCKED — ENVIRONMENT**, not passing and not
failing. The web build and the full Flutter test suite both run clean here and
are what the client is verified by.

---

## Round 6 — Stage 6 (documentation truth pass)

Only real contradictions were changed, each verified against the code first.
`docs/RUNBOOK.md` was corrected in Round 4 alongside the backup work.

### 48. `docs/API.md` documented five endpoints that do not exist — P1

The permission table listed `POST /attachments/presign`,
`POST /attachments/{id}/complete`, `GET /attachments/{id}/url`,
`DELETE /attachments/{id}` and `GET /ai/proposals/{id}`, each with permission
marks implying they were live and secured. None is mounted. It also documented
`GET /dashboard` and `GET /audit`, where the real routes are
`/dashboard/digest` and `/audit-logs`, plus widget endpoints removed in Round 5.

A permission table naming endpoints that do not exist is worse than no table:
the natural reading is that they exist and are protected.

`GET /ai/proposals/{id}` was **found by the guard test below**, not by reading
— I had not spotted it. A proposal reaches the client inline in the message
response; only `/apply` and `/cancel` were ever built.

### 49. The documented manager audit rule was wrong in the permissive direction — P1

§8 stated "managers see only their own actions". The implementation filters by
`audit_read_service._viewable_page_ids` — **every entry for a page the manager
can view**, including other people's actions. Entries with no `page_id`
(logins, user management) are Owner-only.

That is materially wider access than documented, and documentation that
understates access is the dangerous direction to be wrong in.

### 50. A guard so this cannot silently drift again — the durable part

`tests/test_api_docs_match_routes.py` parses API.md's permission table and
asserts every path resolves to a registered route, walking FastAPI's
`_IncludedRouter` indirection the same way `test_permissions_matrix.py` does.
It also asserts the specific removed/unbuilt endpoints never reappear, and
guards against its own regex silently matching nothing.

Prose does not fail a build, which is why this drift accumulated until someone
read it. Now it does.

### 51. Smaller corrections

- **Attachments** are marked "designed, not built" in §6, which previously read
  as a live sequence diagram. The `ATTACHMENT` column type was also removed
  from a live page-creation example.
- **`PROJECT_DOCUMENTATION.md`** listed `backup_dump.sh`, `restore_drill.sh`
  and `seed_demo.py` as "⛔ Empty placeholder files". All three now work and
  have been run.
- **`docs/ADR/0001`** still cited `page_validations` as the mechanism enforcing
  cross-column rules. That table was dropped in migration `0014`, so those
  rules are now enforced **nowhere** — amended to say so rather than quietly
  dropping the sentence.
- **`docs/IMPLEMENTATION_PLAN.md`**'s removal notice was incomplete and in one
  place wrong: it said only widget *creation* had been removed and that an
  Owner could "still PATCH/DELETE an existing widget". Rewritten as a table of
  what was removed, when, and which named files no longer exist. The historical
  phase rows were deliberately left alone — the document is a phase log, and
  rewriting history to match the present would destroy its only purpose. Two
  requirement rows citing deleted files were corrected, including one claiming
  system pages are seeded "on company creation" when no such endpoint exists.
- **Offline `client_uuid`** in §1 described an outbox that was cut. The column
  and its unique index genuinely remain and still de-duplicate a retried
  create, so the behaviour is restated rather than deleted.

---

## Round 7 — Stage 7 (re-audit of the remediation itself)

Two fresh adversarial sweeps were run against the changed code, aimed at the
fixes rather than the original system. **They found five defects in my own
fixes**, three of which were regressions the remediation introduced. Those are
recorded first because they are the ones I owed most.

### 52. Migration 0021's "self-healing" head seeded from zero — P0 (regression)

0021 made the trigger recreate `audit_chain_head` when missing, seeding
`(true, NULL, 0)`. That is right only when `audit_logs` is *also* empty — the
case that prompted it.

With the head lost but the log intact, `last_seq` restarts at 0, the next
insert takes `chain_seq = 1`, `ux_audit_logs_chain_seq` rejects it, and **every
audit insert fails** — which, since every mutation writes one, means every
mutation in the application fails. Exactly the outcome the branch was added to
prevent.

Migration `0023` seeds from `max(chain_seq)` and the matching `row_hash`, and
reconciles a head that is already behind. `audit_chain_head` and `audit_logs`
are documented as one unit: truncating the log alone leaves a `prev_hash` no
row can match, and the verifier then reports permanent tampering.

### 53. The regex cast guard could not be made correct — P1 (regression)

`_guarded_cast` originally guarded each JSONB cast with a regex.
`_DATE_TEXT` was unanchored and range-blind, so `2024-13-01`, `2024-02-30` and
`2024-01-15 <garbage>` all passed the guard and still raised on `::date` — the
page bricked exactly as before, in the scenario the guard existed for. And
every rule added to tighten it risked rejecting a genuinely valid value, which
reads as NULL and looks like data loss.

Migration `0024` adds `velmart_try_numeric/date/boolean`, which perform the
cast and return NULL on failure. "Can Postgres cast this?" has one reliable
answer, and it is not a regex.

**Measured cost, at 100k rows.** plpgsql `EXCEPTION` blocks open a
subtransaction per row, and it shows:

| Benchmark | Regex guard | Try-cast | Target |
|---|---:|---:|---:|
| generic: filter + sort | 144 ms | **198 ms** | 400 ms |
| generic: aggregate over FORMULA | 48 ms | **78 ms** | 400 ms |
| generic: running balance | 236 ms | **347 ms** | 400 ms |
| native page: filter + sort | 77 ms | 93 ms | 400 ms |
| native page: aggregate | 48 ms | 63 ms | 400 ms |

Kept anyway: the cheaper version was incorrect, and the cost stays inside the
target. Native pages are unaffected (real typed columns, no JSONB cast), and
an indexed column uses its projection slot, which bypasses this path
entirely — that is the mitigation available if the margin ever matters.

### 54. Widening search to SELECT introduced a new 500 — P1 (regression)

`cheques.cheque_status` is a SELECT column on the page schema but a Postgres
**enum** in the native table (migration 0008). There is no implicit
enum-to-text cast, so `ilike` on it raised
`operator does not exist: cheque_status ~~* unknown`.

So search and `contains` on the Cheques page 500'd — **inside the guard added
to turn that exact class of 500 into a 422.** Both paths now cast to text
first, which is a no-op for text and correct for an enum.

### 55. `column_values` returned non-strings and 500'd — P1 (regression)

Switching from `str(v)` to `to_wire_value` was right for formatting and wrong
for the response model: `ColumnValuesResponse.values` is `list[str]` and
Pydantic v2 does not coerce. `to_wire_value` passes a BOOLEAN through as a
real `bool` and a FORMULA result as a `Decimal`, so the filter picker 500'd on
any page with either. Now wrapped so booleans render as `true`/`false` and
everything else as its wire string.

### 56. A manager could file a record against any store in the company — P1

`_resolve_store_id` returned the page's STORE_REF column value *before* any
authorization. `validate_references` proves the store belongs to the company,
which is a different question from whether this manager may use it — so the
assignment check added for the body-supplied `store_id` was bypassed simply by
setting the page's own store column instead. Both sources now go through the
same check.

### 57. `store_id` could never be cleared — P1

`update_row` wrote `store_id` only when it was not `None`, so clearing a
page's store column left `records.store_id` pointing at the old store — the
precise stale-scoping bug the update path was changed to eliminate. An
explicit clear now wins.

### 58. The denial audit could fail the request or exhaust the pool — P1 (regression)

`_audit_denial` opens a second connection while the request still holds its
own. With `DB_POOL_SIZE + DB_MAX_OVERFLOW` slots, a burst of denials — the
exact scenario a permission probe produces — could take every slot with each
waiting for another. It also had no `try/except`, so a failed audit write
replaced a clean 403/404 with a 500.

Now bounded by a timeout and never re-raising: the refusal is the correct
answer and must not become a 500 because the audit could not be written. A
lost audit row is logged rather than silent. `require_owner`'s now-unused
session dependency was removed.

---

## Verified correct on re-audit (no change needed)

Recorded because "we checked and it holds" is worth as much as a finding:

- **Keyset NULL pagination** — ascending, descending, earlier-key-null and the
  hardcoded-`desc` id tiebreaker were all worked through; no skip or duplicate.
- **`running_balance` with a limit** — Postgres evaluates window functions
  after `WHERE` and before `ORDER BY`/`LIMIT`, so the balances accumulate over
  all active rows and `reversed()` restores chronological order. The figures
  are right.
- **Cross-tenant idempotency** is genuinely closed — migration 0017 makes an
  unscoped lookup impossible to compile against the primary key.
- **`write_audit_log`'s RLS skip** — every caller was traced and is inside an
  armed transaction.
- **`_client_ip` proxy indexing** — `chain[-hops]` is correct; a prepended
  forgery lengthens the chain without shifting the trusted position.
- **`_meter_ai_request`** — no double-count, no leaked connection.
- **No references remain** to `dashboard_widget`, `validation_service`,
  `pagination.py` or `export_service`.

---

## Correction to an earlier finding

**Round 1 claimed there was "no seed script" and that `tests/conftest.py`
referenced a `seed_demo.py` that did not exist. That was wrong.**
`infra/scripts/seed_demo.py` exists, calls `register_system_pages`, and the
conftest comment was accurate. The original search was scoped to `apps/api/`
and never looked in `infra/`.

The underlying gap is real but narrower than stated, and is restated here so
the wrong version does not stand:

`seed_demo.py` is a **hardcoded demo seeder** — fixed company name, fixed
owner email, fixed password `change-me-now-please`. It cannot provision an
arbitrary company, and its own docstring says so: *"There is no live
`POST /companies` endpoint anywhere in this codebase yet."* So onboarding a
real second company means editing the script's constants, and there is no
supported way to repair a company that already exists without its system
pages.

That state is not hypothetical. The live database holds **`Kandy Test
Traders` with 0 pages** beside `Velmart Demo Supermarket` with 8 — a company
created by some other route that never received system pages, and which the
application offers no way to fix.

---

## Round 8 — closing R1 (the CI gate)

`FINAL_VERIFICATION_REPORT.md` flagged this as the top blocker to a release
assessment: CI verified none of the five migrations added during this audit,
and a stale lockfile or a dead scaffold guard could both go unnoticed.

### 59. CI never gated the migrations, the lockfile, or `alembic/`'s types — R1

**`.github/workflows/api-ci.yml`** gained:

- `uv lock --check` before `uv sync --frozen` — the sync step trusts the lock
  as-is, so a `pyproject.toml` dependency bump nobody re-locked would install
  silently rather than failing the build.
- `mypy app/ alembic/` (was `app/` only). `alembic/` was already clean; now
  it's enforced rather than incidental.
- A new `migrations` job: a plain Postgres 18 service (not testcontainers —
  this checks a property of the migration files themselves, not the app's own
  fixtures) that asserts **exactly one head**, then runs
  `upgrade head` → `downgrade base` → `upgrade head` against a genuinely fresh
  database. This is the check that would have turned #52 (a migration that
  broke every audit write once the chain-head row was empty) into a red CI
  run instead of something found by 407 failing tests.

**`.github/workflows/mobile-ci.yml`** lost its "skip if no pubspec.yaml"
guard, which gated every step behind the file's existence. `apps/mobile` has
been a real Flutter app since P1 — there was no scaffold state left to guard
for — and the guard's actual effect was that deleting `pubspec.yaml` would
have made this workflow report green having run zero checks.

**Verified locally before being wired in**, not just written: ran the exact
`uv lock --check`, `mypy app/ alembic/`, single-head check, and
upgrade→downgrade→upgrade sequence against a fresh throwaway Postgres 18
container, matching what the new job does. All clean.

**Deliberately not done in this round:** `mypy tests/` still has 41
pre-existing errors across 16 files (unrelated to anything in this audit) and
is not yet in the gate — see "Still open" below.

---

## Still open (found, not yet fixed)

Recorded here rather than dropped. Everything listed in earlier rounds as
deferred has since been closed; this is what remains.

**Tooling**

- **`mypy tests/` has 41 pre-existing errors** across 16 files — mostly
  missing parameter annotations and a couple of genuine `Iterable`/`Any`
  typing gaps, none related to this audit. Out of scope for #59; `tests/` is
  not yet in the CI type-check gate because of it.

**Concurrency**

- **`DELETE /records/{id}` does not honour a client `If-Match`.** It is now
  guarded by the version on the handle it just read, so it cannot lose a
  write — but it ignores a version the caller supplies, so a client cannot
  say "delete only if unchanged since I looked".
- **Users, stores and page-access grants carry no version at all.**
  `bump_schema_version` was scoped to the page and its columns, which is what
  `pages.version` actually describes; those three have no equivalent column,
  so concurrent edits to them still last-write-wins.

**AI**

- **Cost accounting still shares the request transaction.** The rate limit is
  now durable (#30), but `AiMessage.cost_usd` is written in the transaction a
  pipeline failure rolls back, so spend from a failed request is not counted
  against the daily cap.
- **Two DB transactions stay open across OpenRouter calls.**
  `POST /ai/sessions/{id}/messages` depends on both `get_rls_session` and
  `get_ai_reader_session`, so two pooled connections sit idle-in-transaction
  for the full model latency. `statement_timeout` is set; nothing bounds
  idle-in-transaction.
- **A zero-item proposal can be marked APPLIED.** An `AppError` raised after
  `_create_proposal`'s first flush is swallowed into `{"error": ...}`, leaving
  a proposal with no items that `apply_proposal` will still complete.

**Query engine**

- **A projected DATE column is compared against a datetime in the cursor.**
  `_populate_projections` truncates a `datetime` to `.date()` when filling a
  `date_*` slot, but `_row_value` reads the untruncated ISO string back out of
  `row.data`, so a DATETIME column with a projection slot can skip rows at a
  page boundary. Not yet reproduced in a test.
- **`find_record` probes seven tables in sequence** for a bare record id, and
  a generic row always wins a UUID collision silently.
