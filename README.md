# Velmart

**AI business data-management and accounting platform for a supermarket.**

Six core business tables ship with the product — Employee Salary, Purchases, Expenses, Daily
Revenue, Cash Ledger and Cheques — and the Owner creates any further tables they need through a
runtime page engine. Money is `Decimal` end to end, every mutation is audited on an append-only
hash chain, and the AI can only propose changes that the Owner applies.

- **Source of truth:** [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) (v4.1)
- **How it is built:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **API contract:** [`docs/API.md`](docs/API.md)
- **Decisions:** [`docs/ADR/`](docs/ADR/)
- **What to build next:** [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | latest | Python packaging; installs Python 3.13 itself |
| Docker | any recent | Runs PostgreSQL 18 locally and backs the integration tests |
| Flutter | 3.47.x | Client only — not needed to run the API |

## Running the API locally

```bash
# 1. Start PostgreSQL 18
docker compose -f infra/docker-compose.yml up -d postgres

# 2. Install dependencies (creates .venv, pinned to Python 3.13)
cd apps/api
uv sync

# 3. Configure
cp .env.example .env        # defaults already point at the local Postgres
                            # set JWT_SECRET_KEY to a real random value:
                            #   python -c "import secrets; print(secrets.token_urlsafe(64))"

# 4. Apply migrations — never part of the start command (plan §23.6)
uv run alembic upgrade head

# 5. Run
uv run uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/health          # {"status":"ok"}
curl localhost:8000/health/ready    # {"status":"ready", ...} once migrated
open http://localhost:8000/docs     # OpenAPI, development only
```

`/health/ready` returns **503** until `alembic upgrade head` has run — that is deliberate, and it
is what stops a broken deploy replacing a working one.

## Tests

```bash
cd apps/api
uv run pytest              # integration tests spin up a real Postgres via testcontainers
uv run ruff check app/ alembic/
uv run mypy app/
```

Docker must be running — the suite tests against real PostgreSQL, not mocks.

## Database

The schema is hand-authored in `apps/api/alembic/versions/`. Migrations manage **platform tables
plus the six core business tables** and nothing else; a seventh business domain is an Owner-created
page, not a migration.

```bash
uv run alembic upgrade head      # apply
uv run alembic downgrade base    # reverse (destroys local data)
```

Three database roles, per plan §8.8:

| Role | Purpose |
|---|---|
| `app_user` | The application. Read/write, no DDL, **cannot** UPDATE/DELETE/TRUNCATE `audit_logs` |
| `ai_reader` | AI read path only. `SELECT` with an 8s timeout; cannot see `users`, `refresh_tokens`, `idempotency_keys` |
| `migrator` | Alembic |

## Layout

```
apps/api/          FastAPI backend
  app/core/        money, dates, security, permissions, expressions
  app/models/      SQLAlchemy — platform tables + business/ (the six)
  app/services/    business logic; the page engine lives here
  alembic/         hand-authored migrations
apps/mobile/       Flutter client (Android, iOS, macOS, Windows)
infra/             Dockerfile, docker-compose, Railway config
docs/              plan, architecture, API, runbook, ADRs
```

## Non-negotiables

Full list in plan §31; the ones most easily broken by accident:

1. **Money never touches a float.** `NUMERIC(14,2)` → `Decimal` → `int` minor units in Dart.
2. **Permissions are enforced in FastAPI before any query runs.** Flutter only hides buttons.
3. **No `eval`/`exec`** for formulas, validations or filters; column keys are validated against
   `page_columns`, never interpolated into SQL.
4. **The audit log is append-only and hash-chained**, written by a database trigger.
5. **The AI never writes to the database** — only the Owner's UPDATE button does.
