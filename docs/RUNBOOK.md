# Velmart — Operations Runbook

**Audience:** Whoever is on call. In V1 that is one developer and, for business decisions, the Owner.
**Scope:** Incident response, backup, restore, and routine maintenance.
**Source:** [PROJECT_PLAN §23, §25](PROJECT_PLAN.md) · [ADR 0003](ADR/0003-railway-only-infrastructure.md)

> **First principle:** this system holds a business's financial records. When in doubt, **stop
> writes and take a snapshot before investigating**. A few minutes of downtime is cheap; corrupted
> or lost records are not.

---

## 1. System at a glance

| Service | What it is | Where |
|---|---|---|
| `api` | FastAPI + Uvicorn, 1 replica, 2 workers | Railway project `velmart`, region `asia-southeast1` (Singapore) |
| `postgres` | PostgreSQL 18, daily backups + PITR | Railway, **private network only** — no public endpoint |
| `bucket` | S3-compatible object storage (attachments, exports) | Railway, private, presigned URLs only |
| `cron` | `python -m app.tasks.nightly` | Railway cron |

**External dependencies:** OpenRouter (LLM), Sentry (errors), an uptime monitor on `/health`.

### Health endpoints

| Endpoint | Meaning |
|---|---|
| `GET /health` | Process is alive. Watched by the uptime monitor at 1-minute intervals |
| `GET /health/ready` | Database reachable and migrations at head. **Railway gates traffic on this** |

### Emergency levers

| Lever | Effect | How |
|---|---|---|
| **AI kill switch** | Stops all AI immediately, **no deploy** | `company_settings.ai_enabled = false` |
| **Session kill** | Invalidates every session for a user instantly | Bump `users.token_version` |
| **Rollback** | Restore the previous working build | Railway → Deployments → previous → Redeploy |
| **Spend limit** | Caps runaway cost | Railway workspace setting (must already be set) |

---

## 2. Incident response

### 2.1 First five minutes (any incident)

1. **Is it up?** Check `/health` and `/health/ready`, then the Railway deploy status.
2. **What changed?** Look at the most recent deployment and the most recent migration. Most
   incidents follow a change.
3. **Is data at risk?** If yes → §2.6 *Suspected data corruption* **first**. Everything else waits.
4. **Note the time.** You will need the window later for audit and PITR.

### 2.2 API is down

1. Railway → `api` → Deployments. Did the latest deploy fail its healthcheck?
2. If a bad deploy: **roll back to the previous deployment**. Do not debug forward in production.
3. If the deploy is healthy but the service is not: check logs for boot failure. `config.py`
   validates every environment variable at boot — a missing secret crashes the container
   immediately and by design.
4. Check database connectivity: `/health/ready` fails when Postgres is unreachable or migrations
   are not at head.
5. If Postgres itself is down, check the Railway status page before assuming it is your fault.

### 2.3 API is slow

1. Long-running queries:
   ```sql
   SELECT pid, now() - query_start AS duration, state, left(query, 120)
   FROM pg_stat_activity
   WHERE state <> 'idle' AND now() - query_start > interval '5 seconds'
   ORDER BY duration DESC;
   ```
2. Pool exhaustion: `DB_POOL_SIZE` is 5 with 5 overflow. Compare active connections against that.
3. Terminate a genuine runaway (note the `pid` and the query first):
   ```sql
   SELECT pg_cancel_backend(<pid>);      -- try this first
   SELECT pg_terminate_backend(<pid>);   -- only if cancel does not work
   ```
4. If it is a `records` query, check whether the page is filtering on a **non-indexed** column. The
   fix is usually for the Owner to mark that column indexed (allocating a projection), not an index
   hand-added in production.

### 2.4 Database connection exhaustion

Symptom: intermittent 500s, `TimeoutError` acquiring a connection. Check for a leaked session (a
service holding a transaction open across an `await` on an external call). The AI read path uses the
separate `ai_reader` role with an 8-second statement timeout — if that role is the one exhausting
connections, disable AI (`ai_enabled = false`) to isolate it while you investigate.

### 2.5 AI spend spike

1. **`ai_enabled = false`** in `company_settings` — takes effect immediately, no deploy.
2. Inspect cost by session:
   ```sql
   SELECT s.id, s.title, s.total_cost_usd, count(m.id) AS messages
   FROM ai_sessions s LEFT JOIN ai_messages m ON m.session_id = s.id
   WHERE s.started_at > now() - interval '7 days'
   GROUP BY s.id ORDER BY s.total_cost_usd DESC LIMIT 20;
   ```
3. Check `ai_model_config` — a routing change sending simple lookups to a frontier model is the
   usual cause.
4. Re-enable only after the daily cap (`ai_daily_usd_cap`) is confirmed correct.

### 2.6 Suspected data corruption

**This is the one that matters. Follow it in order.**

1. **Stop writes.** Scale the API to zero replicas, or disable logins. Do not "keep it running while
   we look".
2. **Snapshot immediately** — before any investigation, so the current state is preserved even if it
   is wrong.
3. **Identify the window** from `audit_logs`. Every mutation is there, with before/after values:
   ```sql
   SELECT created_at, actor_user_id, action, entity_type, entity_id, source, old_data, new_data
   FROM audit_logs
   WHERE created_at BETWEEN :from AND :to
   ORDER BY id;
   ```
4. **PITR restore into a scratch database** — never over production.
5. **Diff** the scratch copy against production for the affected pages and reconcile.
6. Repair forward through the API where possible, so the repair is itself audited.

### 2.7 Audit chain break

The nightly job verifies the hash chain and alerts on any break. A break means a row was altered or
removed **outside** the application, since `app_user` has `UPDATE`, `DELETE`, and `TRUNCATE` revoked
on `audit_logs` and rows are hashed by a database trigger.

1. Find the first bad row — the verifier reports its `id`.
2. Treat this as a **potential credential compromise**, not a bug: go to §2.9.
3. Compare against the most recent `pg_dump` in the bucket to see what the row said before.
4. Do not "repair" the chain. Its value is that it cannot be quietly repaired. Record the break, the
   window, and the finding.

### 2.8 A page schema change broke data entry

The Owner changed a column and entry now fails. The audit log holds the **old column definition** —
schema changes are audited as heavily as data changes.

1. Find it: `SELECT * FROM audit_logs WHERE entity_type = 'page_column' ORDER BY id DESC LIMIT 20;`
2. Restore the definition **through the API**, not by hand in SQL, so the restoration is validated
   and audited.
3. Remember `key` is immutable — if the Owner archived a column, un-archive it rather than
   recreating it under a new key, or every existing value orphans.

### 2.9 Credential leak

1. Rotate the affected value in **Railway variables**, then redeploy.
2. If it was `JWT_SECRET_KEY`: every token is now invalid — expected, users log in again.
3. Bump `token_version` for all users: `UPDATE users SET token_version = token_version + 1;`
4. If it was a database credential: rotate the role's password. Postgres has no public endpoint,
   which narrows the exposure considerably.
5. Review `audit_logs` for the exposure window, paying attention to `PERMISSION_DENIED` entries —
   repeated denials are a signal.

### 2.10 Lost or stolen device

1. Revoke that device's refresh tokens (`refresh_tokens.revoked_at`, matched by `device_id`).
2. Bump the user's `token_version` to kill the 15-minute access token immediately.
3. The local cache is SQLCipher-encrypted and cleared on logout, but treat cached records from the
   last 60 days as exposed.

---

## 3. Backup

| Layer | Mechanism | Frequency | Retention |
|---|---|---|---|
| Postgres | Railway managed backups | Daily | 30 days |
| Postgres | Point-in-time recovery (continuous WAL) | Continuous | Per plan |
| Postgres | `pg_dump` via the nightly cron service | Daily 02:00 SLT (20:30 UTC) | 90 days |
| Postgres | **Off-platform copy on the Owner's drive** | Weekly | 12 months |
| Bucket objects | _Not implemented_ — no storage layer; dumps stay on a local volume | — | — |
| Audit log | As above + nightly chain verification | — | 7 years |

The off-platform weekly copy exists because "our hosting provider had a bad day" is a real risk, and
the business cannot re-derive three years of records from anywhere else.

> **Specific to this architecture:** the Owner's **page definitions are as valuable as the
> records**. A backup that restores `records` but loses `pages` and `page_columns` restores
> meaningless JSONB. Both live in the same database and the same dump — and the restore drill must
> verify **schemas as well as row counts**.

### Objectives

- **RPO ≤ 1 hour** (via PITR) · **RTO ≤ 4 hours**

---

## 4. Restore drill — quarterly

**An untested backup is a hypothesis. The drill converts it into a plan.** Run it quarterly and
record the result in §5 below.

1. **Provision a scratch environment.** Never restore over production.
2. **Restore** the most recent nightly dump (or a PITR target) into it.
3. **Verify row counts per page:**
   ```sql
   SELECT p.name, count(r.id) AS records
   FROM pages p LEFT JOIN records r ON r.page_id = p.id AND r.is_deleted = FALSE
   GROUP BY p.name ORDER BY p.name;
   ```
4. **Verify every page's column definitions** — count and spot-check types, options, protected
   flags, and formulas against production:
   ```sql
   SELECT p.key, c.key, c.data_type, c.is_protected, c.config
   FROM pages p JOIN page_columns c ON c.page_id = p.id
   WHERE c.is_archived = FALSE ORDER BY p.key, c.position;
   ```
5. **Run audit chain verification** against the restored database.
6. **Known-value spot checks** — pick three records with figures the Owner recognises and confirm
   they are exactly right, including formula columns recomputing correctly.
7. **Record the wall-clock time** in the drill log. If it exceeds the 4-hour RTO, that is a finding
   requiring action, not a footnote.
8. Tear the scratch environment down.

---

## 5. Restore drill log

Record every drill here. This table is the evidence that the RTO is real.

Run it with `infra/scripts/restore_drill.sh`, which performs steps 1-2 and
5-8 automatically and exits non-zero if the restored copy fails verification.

For a drill at realistic volume rather than whatever the database happens to
hold, seed one first:

```
uv run python infra/scripts/seed_rto_drill_data.py --seed      # ~100k rows/table, ~8s
infra/scripts/backup_dump.sh
infra/scripts/restore_drill.sh
uv run python infra/scripts/seed_rto_drill_data.py --cleanup <company_id>
```

`--cleanup` removes the seeded company and everything cascaded from it, but
deliberately leaves its handful of audit-log entries in place — the hash
chain is one global sequence across every company, and deleting from the
middle of it would break the chain for every tenant, not just the synthetic
one. Deleting `records` at this volume is genuinely slow (its GIN and
trigram indexes cost real time to maintain on delete — measured at 2m19s for
100,000 rows, against 67ms for the same row count in an index-light native
table); the script accounts for this with its own longer timeout, so this is
expected, not a hang.

| Date | Performed by | Restore source | Wall-clock time | Rows verified | Schemas verified | Chain OK | Findings |
|---|---|---|---|---|---|---|---|
| 2026-09-19 | Automated (`restore_drill.sh`), local Docker Postgres 18 | `velmart-20260919T142033Z.dump` (138 KB, 260 objects) | **3s** | 458 across 29 tables | Yes — migration head `0021` matched, all tables present with equal row counts | Yes | First drill ever performed. Both scripts were 0-byte files until this date, so no backup had ever been taken and the 4-hour RTO had never been measured. Dataset is development-sized; the 3s figure does **not** validate the RTO at production volume. |
| 2026-09-23 | Automated (`restore_drill.sh`), local Docker Postgres 18, against `infra/scripts/seed_rto_drill_data.py`-seeded volume | `velmart-20260923T052021Z.dump` (6.6 MB, 255 objects) | **3s** | 200,540 across 28 tables | Yes — migration head `0025` matched, all tables present with equal row counts | Yes | Second drill, at realistic volume: 100,000 rows in `records` (generic JSONB page — GIN + trigram indexes, a projection slot, a `FORMULA` column) and 100,000 in `expenses` (native system table), the same 100k figure `tests/perf/test_volume.py` and the project's own volume target both already treat as production-representative. Source database was 91 MB. Drill data removed afterward (`--cleanup`); dev database confirmed back to its prior state and the audit chain confirmed still valid. |

> **Neither measured time above is the RTO**, for different reasons.
>
> The first (2026-09-19) proved almost nothing beyond "the procedure runs" —
> 458 rows is not a volume any real restore would be measured against.
>
> The second (2026-09-23) is a genuine improvement — 3 seconds to restore and
> fully verify 200,540 rows / 91 MB is a real, useful lower bound on the
> **restore-and-verify step itself**, at this project's own definition of
> production-representative volume. It is still not the RTO, because it
> measures none of the following, each real time a production incident would
> spend: retrieving the backup from off-platform storage (there is none yet —
> see §3's "Bucket objects: Not implemented"), provisioning a fresh database
> instance on Railway, and repointing the application at it. Source and
> destination were also the same machine, so no network transfer time is
> reflected at all.
>
> Re-run this drill against real off-platform storage and real Railway
> infrastructure once both exist before treating the 4-hour RTO as evidenced.
> Until then, what is evidenced is narrower and stated precisely above rather
> than rounded up to "the RTO is fine."

---

## 6. Routine maintenance

### Nightly cron (`python -m app.tasks.nightly`)

Deployed as a **separate Railway service** from `infra/railway.cron.json`
(`railway up --config infra/railway.cron.json`), because Railway models a cron
as its own service with a `cronSchedule`. Locally:
`docker compose -f infra/docker-compose.yml run --rm nightly`.

It requires `DATABASE_URL_MIGRATOR` (the schema-owning role, needed for a
complete `pg_dump`) and `BACKUP_DIR` pointing at a mounted volume. Without
`BACKUP_DIR` the dump is written to a temp directory and discarded on the next
redeploy; the task logs `backup.not_persistent` when that happens.

| Task | Module | Purpose |
|---|---|---|
| Audit chain verify | `app/tasks/audit_chain_verify.py` | Detect tampering; alert on any break |
| `pg_dump` backup | `app/tasks/export_build.py` (`infra/scripts/backup_dump.sh` for manual runs) | 90-day retained logical backup to `BACKUP_DIR`. **Not** uploaded to a bucket — there is no storage layer, so this is a local/volume copy only. |
| Idempotency cleanup | `app/tasks/idempotency_cleanup.py` | Remove keys older than 48h |
| Daily digest | `app/tasks/daily_digest.py` | Pages with no records in N days, `needs_review` records, chain breaks, AI spend. (Failed imports and unsynced outboxes are listed in older copies of this table; both features were removed.) |

**Check the digest each morning.** It is the business monitor — Prometheus is unnecessary at three
users, so the digest plus Sentry is the observability story.

### Deploys

- **Migrations run as a pre-deploy step**, never in the app's start command.
- **Expand/contract only** — no destructive single-step schema changes.
- The healthcheck gates traffic: Railway routes to a new deployment only after `/health/ready`
  returns 200.
- Migrations touch **platform tables only**. Owner pages are data and are never migrated.

### Weekly

- Confirm the off-platform backup copy actually ran and is readable.
- Review the review queue (`needs_review` records) with the Owner.
- Check Sentry for new error signatures.

### Quarterly

- Restore drill (§4).
- Review page-access grants — the manager should see exactly what they should, no more.
- `pip-audit` / dependency review.

---

## 7. Escalation

| Situation | Who decides |
|---|---|
| Roll back a deploy | On-call developer — do it, then report |
| Stop writes / take the system down | On-call developer — data safety outranks uptime |
| Restore production from backup | Owner must be informed **before** it happens; any writes since the restore point are lost |
| Reconcile disputed figures | Owner — with the audit log as evidence |
| Turn the AI off | Either. It is reversible and costs nothing |

**Rollback plan for the business:** if the system is unavailable for a working day, the shop falls
back to the spreadsheets for that day and the records are entered afterwards. This is written down
so it is a decision already made rather than one taken under pressure.
