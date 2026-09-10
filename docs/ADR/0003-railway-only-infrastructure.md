# ADR 0003 — Railway-only infrastructure, sized for three users

- **Status:** Accepted
- **Date:** 2026-09-10
- **Deciders:** Owner, lead developer
- **Related:** [PROJECT_PLAN §5.1](../PROJECT_PLAN.md), §23, §27

## Context

An earlier draft split the system across two providers: Supabase for database, auth, and storage,
plus Railway for compute. That means two clouds, two identity systems, cross-region latency on every
query, and two bills.

The same draft specified Redis, an ARQ worker service, SSE realtime, two API replicas, and PR
environments — roughly $40–60/month and four additional things that can fail at 2 a.m., for a system
serving **one supermarket and at most three users**.

## Decision

**Railway only, one region, one of everything.**

| Service | Purpose | Sizing |
|---|---|---|
| `api` | FastAPI + Uvicorn | 1 replica, ~0.5 vCPU / 512 MB, healthcheck `/health/ready` |
| `postgres` | Railway PostgreSQL 18 | Small instance, 10 GB volume, backups + PITR on, **private only** |
| `bucket` | Railway Bucket (S3-compatible) | Private, presigned URLs only |
| `cron` | `python -m app.tasks.nightly` | Audit chain verify, `pg_dump` to bucket, idempotency cleanup, daily digest |

- **Region: `asia-southeast1-eqsg3a` (Singapore).** ~45–70 ms round trip from Colombo versus
  220–280 ms to US West. On a screen issuing several requests that is the difference between
  "instant" and "laggy", and managers who find the app slow go back to paper.
- **Auth is FastAPI-issued JWT** with Argon2id and rotating device-bound refresh tokens. No
  third-party identity provider.
- **Environments: `production` only**, plus a local Docker Compose stack for development.
- **Rate limiting and idempotency live in Postgres**, not Redis. At three users the table will not
  become a bottleneck.
- **Background work** is FastAPI `BackgroundTasks` plus one Railway cron job.

Explicitly ruled out for V1: Kubernetes, AWS multi-service architecture, multiple API replicas,
microservices, message brokers, Redis, a separate worker, SSE/realtime, and a fleet of environments.

## Consequences

**Positive**

- One provider, one bill, one private network. Postgres and the bucket have **no public endpoint**.
- Total running cost ≈ **$40–90/month** including LLM usage.
- Fewer moving parts to monitor, and correspondingly fewer 2 a.m. failures.
- Two Uvicorn workers in one container is ample concurrency for three users and avoids multi-replica
  coordination entirely.

**Negative / accepted costs**

- **Deploys cause a brief interruption.** Acceptable for a three-user shop; the healthcheck still
  gates traffic so a broken build cannot replace a working one.
- **No staging environment.** Production testing is the fallback until the trigger below fires.
- **Provider concentration risk.** "Our hosting provider had a bad day" is real, which is why the
  backup strategy includes a weekly off-platform copy on the Owner's own drive (PROJECT_PLAN §25.2).
- A job that exceeds the request lifetime has nowhere to run until a worker is added.

## When to add infrastructure

Each deferred piece has a **measured trigger**. Add it when the trigger fires, not before.

| Add | Trigger |
|---|---|
| Redis | Measured contention on `idempotency_keys` or rate limiting |
| Background worker (ARQ) | A job regularly exceeds 30 seconds, or must survive a deploy |
| Second API replica | Sustained CPU above 70%, or an uptime requirement during deploys |
| Staging environment | A second developer joins, or testing in production becomes unacceptable |
| SSE / realtime | Users complain data looks stale between refreshes |
| FCM push | When smart alerts ship (V2) |

## Operational rules this ADR creates

1. **Migrations run as a pre-deploy step**, never in the app's start command.
2. **Expand/contract migrations only** — no destructive single-step schema changes.
3. **A spend limit is set on the Railway workspace**, so an incident is a notification rather than
   an invoice.
4. Secrets live only in Railway variables; `.env.example` documents names, never values.
