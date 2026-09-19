# Velmart — Project Documentation

**Purpose of this file:** explain, in plain language, what actually exists in this codebase
right now — not what is planned, not what is aspirational, but what has really been written,
tested, and pushed to GitHub. If you open this project after a break and feel lost, start here.

**How this differs from `docs/`:** the `docs/` folder contains the *plan* — a ~2,700-line
specification (`docs/PROJECT_PLAN.md`) describing the entire system Velmart is meant to become,
including large parts that are **not built yet** (the AI layer, the page engine, CSV import,
attachments, offline sync, and more). This file, `PROJECT_DOCUMENTATION.md`, documents only the
slice of that plan that has actually been implemented and verified so far. When in doubt, trust
this file for "what exists today" and `docs/PROJECT_PLAN.md` for "what the system is meant to be."

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [Project Structure](#4-project-structure)
5. [Code Explanation — File by File](#5-code-explanation--file-by-file)
6. [Important Code Flows](#6-important-code-flows)
7. [APIs and Endpoints](#7-apis-and-endpoints)
8. [Database](#8-database)
9. [Authentication and Security](#9-authentication-and-security)
10. [Deployment and Infrastructure](#10-deployment-and-infrastructure)
11. [Current Project Status](#11-current-project-status)
12. [What We Have Done So Far](#12-what-we-have-done-so-far)
13. [If I Know Nothing About This Project, What Should I Understand First?](#13-if-i-know-nothing-about-this-project-what-should-i-understand-first)

---

## 1. Project Overview

### What is this project?

**Velmart** is a business data-management and accounting application, built for one specific
supermarket in Sri Lanka. Think of it as a smarter, safer replacement for a shop's paper ledgers
and spreadsheets — a phone/computer app where the shop owner and their managers record money
coming in and going out, and later an AI assistant will be able to answer questions about that
data (like "how much did we spend on electricity this month?").

It has two halves:

- **A backend** (`apps/api/`) — a server written in Python that stores all the data in a
  database and enforces every rule ("a manager cannot delete a record", "money must be exact to
  the cent", etc.).
- **A client** (`apps/mobile/`) — an app written in Dart/Flutter, meant to run on phones,
  tablets, and desktop computers (Android, iOS, macOS, Windows), that people actually tap and
  type into.

The backend is the "brain and memory" — it holds the real data and makes every decision about
what's allowed. The client is the "face" — it shows screens and sends requests, but never decides
anything on its own. This split matters a lot for security, and you'll see it repeated throughout
this document: **the server is the only thing that can be trusted.**

### The main purpose of the system

1. Let the shop **record money movements** — salaries paid, purchases made, expenses incurred,
   daily revenue, cash on hand, and cheques issued.
2. Keep those records **safe and honest** — every change is logged permanently, money is never
   stored in a way that can silently lose a cent, and a manager cannot quietly delete or alter
   something without the owner's approval.
3. Eventually, let an **AI assistant** answer questions about the data and propose changes that
   the owner must explicitly approve before anything is written. **This part does not exist in
   code yet** — it's designed in the plan but not built.

### What we have completed so far (in one sentence each)

- A complete, tested **database design** for the whole system (27 tables, security rules, and an
  audit trail that cannot be tampered with).
- A working **login system** — a real person can log in, get a session, have that session expire
  and refresh automatically, and be logged out — all verified against a real database.
- The **beginnings of a mobile app** — written but not yet compiled or run, because the required
  tools (Flutter, Xcode) are not fully installed on the development machine yet.
- **Nothing yet** for the actual business features (recording expenses, salaries, purchases,
  etc.) at the code level — the database tables for these exist, but no backend code reads or
  writes them yet, and no screens exist for them either.

### Completed vs. partially completed vs. not yet implemented

| Status | Meaning |
|---|---|
| ✅ **Completed** | Code exists, has been run, and has automated tests proving it works |
| 🟡 **Partially completed** | Code exists but has NOT been run/verified (e.g., the mobile app — written but never compiled) |
| ⛔ **Not yet implemented** | Nothing written — just an empty placeholder file, or nothing at all |

| Feature area | Status |
|---|---|
| Database schema (all tables, security rules, audit trail) | ✅ Completed, verified against a real database |
| User login / session refresh / logout | ✅ Completed, 81 automated tests pass |
| Money handling (no floating-point errors) | ✅ Completed, tested on both backend and client |
| Business-day date logic (the "midnight cash-up" rule) | ✅ Completed, tested |
| Rate limiting (stopping someone from guessing passwords) | ✅ Completed, tested |
| Mobile app shell, login screen, secure token storage | 🟡 Written, never compiled or run |
| Recording expenses / salaries / purchases / revenue / cheques | ⛔ Database table exists; no backend code or screens yet |
| Permission system (who can do what) | ⛔ Not implemented — only the simplest "are you logged in" check exists |
| The "page engine" (Owner builds their own custom tables) | ⛔ Not implemented at all |
| AI assistant | ⛔ Not implemented at all |
| CSV import/export, file attachments, offline mode | ⛔ Not implemented at all |
| Deployment to a real server (Railway) | ⛔ Configuration files written, but no live server exists |

### How the different parts work together (in simple terms)

Imagine the shop owner opens the app on their phone:

1. The **Flutter app** (client) shows a login screen.
2. The owner types their email and password and taps "Sign in."
3. The app sends that information over the internet to the **FastAPI server** (backend).
4. The server checks the password is correct, checks the account isn't locked out from too many
   failed attempts, and if everything is fine, creates a "session" — a pair of secret tokens.
5. The server sends those tokens back to the app.
6. The app **saves the tokens in a secure, encrypted vault** on the device (not in a plain file
   anyone could read).
7. From then on, every request the app makes includes one of those tokens, so the server knows
   who's asking and what they're allowed to do.
8. If a token expires, the app automatically asks the server for a fresh one behind the scenes,
   without the user noticing.

That's the entire working slice of the project today. Nothing about expenses, salaries, or any
other business data flows through this yet — only login/session management.

---

## 2. Technology Stack

### Backend (`apps/api/`)

| Technology | What it is | Why we use it | Where it's used |
|---|---|---|---|
| **Python 3.13** | A general-purpose programming language | It's readable, has excellent libraries for web servers and databases, and is what the whole backend plan is written in | The entire `apps/api/` codebase |
| **FastAPI** | A Python framework for building web APIs (a "web API" is a server that answers requests over the internet, usually with JSON data) | Fast, modern, and it automatically validates incoming data against rules we define | `app/main.py`, every file in `app/routers/` |
| **Uvicorn** | The actual program that runs the FastAPI server and listens for network connections | FastAPI needs something to actually run it — Uvicorn is that "engine" | Started via `uvicorn app.main:app` |
| **SQLAlchemy 2.0 (async)** | An "ORM" — a library that lets Python code describe database tables as Python classes, instead of writing raw SQL by hand everywhere | Keeps database code type-safe and consistent; the "async" part means the server can handle many requests at once without getting stuck waiting on the database | Every file in `app/models/`, `app/db/` |
| **asyncpg** | The actual low-level program that talks to PostgreSQL over the network, using the fast "async" style | SQLAlchemy needs a "driver" underneath it to actually send bytes to the database — this is that driver | Wired in via `app/config.py`'s `to_asyncpg_url()` |
| **Alembic** | A tool that tracks database changes over time as a numbered sequence of "migrations" (see [Database](#8-database)) | Lets us change the database structure safely and repeatably, and undo changes if needed | `apps/api/alembic/` — 9 migration files so far |
| **PostgreSQL 18** | The actual database — the software that stores all the data on disk | It's powerful, reliable, and has advanced security features (Row-Level Security) that this project leans on heavily | Runs in Docker locally (`infra/docker-compose.yml`); would run on Railway in production |
| **Pydantic v2** | A library for describing "what shape should this data be" and automatically checking/converting it | Used by FastAPI to validate every incoming request body (e.g., "email must look like an email, password must be a string") | `app/config.py` (settings), `app/schemas/auth.py` (request/response shapes) |
| **Argon2 (via `argon2-cffi`)** | A password-hashing algorithm — turns a password into scrambled, unreadable text that can still be checked for a match | It's the current best-practice way to store passwords; even if the database leaked, passwords couldn't be reversed | `app/core/security.py` |
| **PyJWT** | A library for creating and reading "JSON Web Tokens" — a compact, tamper-proof way to say "this user is logged in" | Used to create the access tokens the app carries around after login | `app/core/security.py` |
| **structlog** | A library for writing log messages as structured JSON instead of plain text | Makes logs machine-readable and searchable, and lets us automatically hide passwords/tokens from ever appearing in logs | `app/core/logging.py`, used everywhere via `get_logger()` |
| **Sentry SDK** | A service/library for automatically capturing and reporting crashes and errors | Lets developers find out about problems in production without a user having to report them | Wired into `app/main.py`, but inactive until a real Sentry account/key is configured |
| **pytest + pytest-asyncio** | The testing framework | Lets us write automated tests that prove the code works, and re-run them any time something changes | Every file in `apps/api/tests/` |
| **testcontainers** | A library that spins up a real, temporary PostgreSQL database (using Docker) just for running tests | We test against a **real database**, never a fake pretend one — this catches real bugs that a "mock" database would hide | `apps/api/tests/conftest.py` |
| **ruff** | A very fast Python linter/formatter (checks code style and catches simple mistakes) | Keeps the code style consistent and catches errors before they matter | Run via `uv run ruff check` |
| **mypy** | A static type checker for Python | Catches a whole category of bugs (wrong data types) before the code ever runs | Run via `uv run mypy app/` |
| **uv** | A modern, fast Python package/dependency manager | Installs all the libraries above and locks their exact versions so the project behaves the same on every machine | `apps/api/pyproject.toml`, `apps/api/uv.lock` |

### Client (`apps/mobile/`)

| Technology | What it is | Why we use it | Where it's used |
|---|---|---|---|
| **Dart** | The programming language Flutter apps are written in | Required by Flutter | The entire `apps/mobile/lib/` codebase |
| **Flutter 3.47** | A framework for building one app that runs on Android, iOS, macOS, and Windows from a single codebase | Avoids writing four separate apps; matches the plan's requirement for four platforms | The whole client project |
| **flutter_riverpod** | A "state management" library — a way of sharing data (like "is the user logged in?") across many screens without messy plumbing | Keeps the app's data flow predictable and testable | `app/core/providers.dart`, `auth_controller.dart` |
| **Dio** | An HTTP client library — the thing that actually sends requests to the backend server over the internet | More powerful than Flutter's built-in HTTP tools; supports "interceptors" (code that runs on every request/response automatically) | `lib/core/network/api_client.dart` and friends |
| **go_router** | A routing/navigation library — decides which screen to show based on a "path" (like a web address) | Lets us redirect users to the login screen if they're not authenticated, cleanly | `lib/routing/` |
| **flutter_secure_storage** | A library that stores small pieces of data in the phone/computer's built-in secure vault (Keychain on Apple devices, Keystore on Android) | Login tokens must never be stored in a plain, readable file — this keeps them encrypted by the operating system itself | `lib/core/storage/secure_store.dart` |
| **uuid** | A library for generating random, unique identifier strings | Used to generate a unique "device ID" the first time the app runs, so the server can tell which physical device a login session belongs to | `lib/features/auth/data/auth_repository.dart` |
| **drift**, **sqlite3_flutter_libs** | A local, on-device database library | Declared for future offline support (storing data on the phone when there's no internet) — **not used by any code yet** | Listed in `pubspec.yaml` only |
| **fl_chart** | A charting/graphing library | Declared for the future dashboard feature — **not used yet** | Listed in `pubspec.yaml` only |
| **flutter_test** | Flutter's built-in testing framework | Used to write automated tests for the Dart code | `apps/mobile/test/core/money_test.dart` |

### Database

| Technology | What it is | Why we use it |
|---|---|---|
| **PostgreSQL 18** | A relational (table-based) database | Chosen for its maturity, and specifically for **Row-Level Security** (a feature that lets the database itself refuse to leak one company's data to another) and its JSON support |
| **Row-Level Security (RLS)** | A PostgreSQL feature where the database checks, on every single query, whether the current "role" is allowed to see a row | This is a second line of defense — even if the application code has a bug, the database itself still won't leak data |
| **Database roles** (`app_user`, `ai_reader`, `migrator`) | Separate database "logins," each with only the permissions it needs | Following the principle of "least privilege" — the AI's future read-only access literally cannot write data, because its database login has no write permission at all |

### AI / LLM technologies

**None yet.** The plan (`docs/PROJECT_PLAN.md` §16–17) describes a future integration with
OpenRouter (a service that gives access to many different AI language models), but **no code
for this exists in the repository.** All the files that would hold this logic
(`apps/api/app/ai/*.py`) are currently empty placeholder files.

### Authentication

Covered in depth in [Section 9](#9-authentication-and-security). In short: Argon2id password
hashing, JSON Web Tokens (JWT) for short-lived sessions, and a separate, longer-lived "refresh
token" for silently renewing sessions — all custom-built, no third-party login provider (no
"Sign in with Google," etc.).

### Hosting / deployment

| Technology | What it is | Status |
|---|---|---|
| **Docker** | A tool for packaging an application and everything it needs to run into a single, portable "container" | ✅ Used for local development (runs PostgreSQL) |
| **Docker Compose** | A tool for describing and running multiple Docker containers together | ✅ `infra/docker-compose.yml` runs PostgreSQL and can run the API |
| **Railway** | A cloud hosting platform where the real, live version of this app is meant to run | 🟡 Configuration file (`infra/railway.json`) is written, but **no actual Railway project/account has been set up** — nothing is deployed |
| **GitHub Actions** | A tool for automatically running checks (tests, linting) every time code is pushed to GitHub | ✅ Three workflow files exist and the first two (`api-ci.yml`, `mobile-ci.yml`) run for real on every push; the third (`deploy-production.yml`) is written but deliberately does nothing until a Railway account exists |

### Development tools

| Tool | Purpose |
|---|---|
| **Git** | Version control — tracks every change to the code over time |
| **GitHub** | Where the code is hosted online (`github.com/Aathi-kshan/VELMART_ACCOUNTING_AGENT`) |
| **`.env` files** | Where secret configuration values (like database passwords) live on each developer's machine — never committed to Git |

---

## 3. System Architecture

### The simplest possible picture of what exists today

```
 Person on a phone/laptop
         │
         │  (taps "Sign in", types email + password)
         ▼
 ┌───────────────────┐        HTTPS request         ┌─────────────────────┐
 │   Flutter Client   │ ────────────────────────────▶│    FastAPI Server   │
 │  (apps/mobile/)     │                              │     (apps/api/)      │
 │                     │◀──────────────────────────── │                      │
 └───────────────────┘        JSON response          └──────────┬───────────┘
                                                                  │
                                                                  │ SQL queries
                                                                  ▼
                                                        ┌───────────────────┐
                                                        │   PostgreSQL 18    │
                                                        │  (in Docker, or    │
                                                        │   Railway later)   │
                                                        └───────────────────┘
```

### What happens when a user logs in (the one real, working flow)

This is the **only** complete, end-to-end flow that exists in the code today. Every other
"flow" in the plan (recording an expense, viewing a dashboard, asking the AI a question) is not
yet built.

1. **User action:** taps "Sign in" on the Flutter login screen after typing an email and
   password.
2. **Client:** `LoginScreen` (in `login_screen.dart`) calls
   `AuthController.login()`, which calls `AuthRepository.login()`.
3. **Network:** `AuthRepository` sends a `POST /auth/login` request via Dio, with the email,
   password, and a device ID.
4. **Server receives it:** FastAPI's `login()` function in `app/routers/auth.py` runs.
5. **Rate limiting check:** before looking at the password at all, the server checks — using
   `app/core/ratelimit.py` — whether this IP address has tried to log in more than 5 times in the
   last minute. If so, it immediately refuses with a "429 Too Many Requests" response.
6. **Business logic:** the router hands off to `auth_service.login()` in
   `app/services/auth_service.py`, which:
   - looks up the user by email in the database,
   - checks if the account is currently locked out,
   - checks the password against the stored Argon2 hash,
   - if wrong, increments a "failed attempts" counter and locks the account for 15 minutes after
     5 failures,
   - if correct, creates a new access token (a JWT) and a new refresh token, and saves a
     permanent audit-log entry recording "this user logged in."
7. **Database:** all of the above involves real reads and writes to the PostgreSQL database
   (the `users`, `refresh_tokens`, and `audit_logs` tables).
8. **Response:** the server sends back the access token, refresh token, and basic user info
   (name, role) as JSON.
9. **Client receives it:** `AuthRepository` saves both tokens into the phone's secure storage
   vault (`SecureStore`), and `AuthController` updates the app's state to "authenticated."
10. **Screen changes:** because the app's routing (`go_router`) is watching that authentication
    state, it automatically redirects from the login screen to the home screen, which then shows
    the user's name and role ("Owner" or "Manager").

### How the pieces talk to each other

There are only two "services" right now — the Flutter client and the FastAPI server — plus the
PostgreSQL database that only the server can see directly. The client **never** talks to the
database directly; it only ever talks to the server over HTTPS, and the server is the only thing
with database credentials. This is intentional and important: it means every rule about who can
do what is enforced in one place (the server), not scattered across every device running the app.

### The "layers" inside the backend

```
Router          → decides the HTTP shape: what URL, what status code, what JSON in/out
   ↓
Dependency      → checks things like "is this a valid, logged-in user?"
   ↓
Service         → the actual business logic and rules
   ↓
Database model  → the Python description of a database table
   ↓
PostgreSQL      → where the data actually lives, with its own security rules (RLS)
```

Right now, only the **auth** slice of this has real code in every layer. Everything else (pages,
records, expenses, etc.) has database tables and Python model classes describing those tables,
but no router, dependency, or service code that actually uses them yet.

---

## 4. Project Structure

This section only documents files and folders that **actually contain code or configuration**.
Hundreds of other files exist as empty placeholders (0 bytes) representing the planned future
structure from `docs/PROJECT_PLAN.md` §22 — those are noted collectively at the end of each
subsection rather than listed one by one, since documenting an empty file's "purpose" would just
be repeating the plan.

### Top level

| Path | Purpose |
|---|---|
| `README.md` | Quick-start guide: how to install dependencies and run the API locally |
| `PROJECT_DOCUMENTATION.md` | This file |
| `.gitignore` | Tells Git which files to never track (secrets, build artifacts, IDE files) |
| `apps/api/` | The Python/FastAPI backend — see below |
| `apps/mobile/` | The Dart/Flutter client — see below |
| `infra/` | Docker and deployment configuration |
| `docs/` | The planning documents (the full specification, architecture notes, decision records) |
| `.github/workflows/` | Automated CI (continuous integration) scripts that run on GitHub |

### `apps/api/` — the backend

| Path | Purpose |
|---|---|
| `pyproject.toml` | Lists every Python library the backend depends on, and configures `ruff`/`mypy` |
| `uv.lock` | The exact, locked versions of every dependency (so installs are reproducible) |
| `.env.example` | Documents every configuration variable the server needs, **with no real values** |
| `.python-version` | Pins the Python version to 3.13 for this project |
| `alembic.ini` | Configuration for the database migration tool |
| `alembic/env.py` | The script Alembic runs to connect to the database and apply migrations |
| `alembic/versions/0001_...` through `0009_...` | The 9 migration files — see [Database](#8-database) |
| `app/config.py` | Reads and validates all environment variables/settings at startup |
| `app/main.py` | Creates the FastAPI application, wires up logging, error handling, and routes |
| `app/core/` | Cross-cutting logic used everywhere: money, dates, security, errors, logging, rate limiting, idempotency |
| `app/db/` | Database connection setup: the read-write engine, the (future) read-only engine, and the Row-Level Security helper |
| `app/dependencies/auth.py` | The "is this a valid logged-in user?" check, reusable across any endpoint |
| `app/models/` | One Python file per group of database tables (27 tables total, described in [Database](#8-database)) |
| `app/routers/health.py` | The `/health` and `/health/ready` endpoints |
| `app/routers/auth.py` | The `/auth/login`, `/auth/refresh`, `/auth/logout`, `/me` endpoints |
| `app/schemas/auth.py` | The exact shape of login/refresh request and response JSON |
| `app/services/auth_service.py` | All the actual login/refresh/logout business logic |
| `tests/conftest.py` | Shared test setup: spins up a real, temporary PostgreSQL database for every test run |
| `tests/test_*.py` (7 files) | The 81 automated tests that currently exist and pass |

**Everything else under `apps/api/app/`** — `ai/`, `core/expressions/`, `core/context.py`,
`core/permissions.py`, `core/pagination.py`, `dependencies/db.py`, `dependencies/guards.py`,
`repositories/`, most of `routers/`, most of `schemas/`, most of `services/`, `storage/`,
`tasks/` — **exists only as empty placeholder files.** They represent where future code will
live, following the exact folder structure the plan describes, but contain zero lines of code
today.

### `apps/mobile/` — the client

| Path | Purpose |
|---|---|
| `pubspec.yaml` | Lists every Dart/Flutter package the app depends on |
| `analysis_options.yaml` | Configures Dart's static analyzer (its version of a linter) |
| `lib/main.dart` | The entry point — the very first code that runs when the app starts |
| `lib/app.dart` | Defines the overall app widget (theme, routing) |
| `lib/core/config/env.dart` | The API server's address (defaults to `localhost:8000` for local development) |
| `lib/core/money/money.dart` | The `Money` class — see [Section 5](#5-code-explanation--file-by-file) |
| `lib/core/network/` | The HTTP client (Dio) and its two "interceptors" (auth token attachment + auto-refresh, and retry-on-failure) |
| `lib/core/storage/secure_store.dart` | Wraps the phone's secure vault for storing login tokens |
| `lib/core/providers.dart` | Wires up the app-wide shared instances (the API client, the secure store) |
| `lib/features/auth/` | Everything related to logging in: the data model, the repository (talks to the server), the controller (manages login state), and the two screens (login, home) |
| `lib/routing/` | `go_router` setup and the logic that redirects between login/home screens |
| `test/core/money_test.dart` | Automated tests for the `Money` class |

**Everything else under `apps/mobile/lib/`** — `core/date/`, `core/permissions/`,
`core/storage/database.dart`, `core/sync/`, `core/widgets/` (besides what's listed), and almost
all of `features/` (AI chat, dashboard, pages) — **exists only as empty placeholder files.**

**Critically:** there are no `ios/`, `android/`, `macos/`, `windows/`, or `linux/` folders yet.
These get generated by running `flutter create` and are required before the app can actually be
compiled and run on any device. This step has not happened.

### `infra/` — deployment configuration

| Path | Purpose | Status |
|---|---|---|
| `Dockerfile.api` | Instructions for building the backend into a Docker container image | ✅ Written, used locally |
| `docker-compose.yml` | Runs PostgreSQL (and optionally the API) locally with one command | ✅ Written and used |
| `railway.json` | Configuration for deploying to the Railway cloud platform | 🟡 Written, but no Railway project exists to use it |
| `scripts/backup_dump.sh` | Verified logical backup with checksum and retention pruning | ✅ Implemented and run |
| `scripts/restore_drill.sh` | Restores into a scratch database and verifies migration head, per-table row counts and the audit chain | ✅ Implemented; first drill recorded in `docs/RUNBOOK.md` §5 |
| `scripts/seed_demo.py` | Provisions a company (`--name/--owner-email/--password`), the demo company (`--demo`), or repairs companies missing system pages (`--repair-all`) | ✅ Implemented and run |

### `.github/workflows/` — automated checks

| Path | Purpose | Status |
|---|---|---|
| `api-ci.yml` | On every push: installs dependencies, runs `ruff`, `mypy`, and the full test suite against a real PostgreSQL | ✅ Runs for real |
| `mobile-ci.yml` | On every push: installs Flutter, runs `dart analyze` and `flutter test` | ✅ Runs for real (using a real Flutter install on GitHub's servers, even though Flutter isn't installed on the local development machine) |
| `deploy-production.yml` | Meant to deploy to Railway after tests pass | 🟡 Written but deliberately does nothing (skips itself) until a `RAILWAY_TOKEN` secret is added |

### `docs/` — the planning documents

These are **not implementation status** — they are the specification the project is being built
against. Useful to know they exist, but they describe the target, not the current state.

| File | What it contains |
|---|---|
| `PROJECT_PLAN.md` | The full, ~2,700-line specification for the entire system |
| `ARCHITECTURE.md` | A more concise explanation of how the system is meant to be built |
| `API.md` | The planned API contract (most endpoints in it don't exist in code yet) |
| `RUNBOOK.md` | Planned operational procedures for when the system is live |
| `ADR/0001` through `0006` | "Architecture Decision Records" — written explanations of major design decisions and why they were made |
| `IMPLEMENTATION_PLAN.md` | A step-by-step build plan broken into phases, with a status tracker |

---

## 5. Code Explanation — File by File

This section covers every file that contains real, working code. Files are grouped by what they
do, and explained in the order you'd naturally want to read them.

### 5.1 `apps/api/app/config.py` — Application Settings

**Overall purpose:** this file defines every configuration value the server needs to run (things
like the database address, the secret key used to sign login tokens, and various limits) and
**validates them the moment the server starts up.** If something important is missing, the
server crashes immediately with a clear error — rather than starting up fine and then failing
mysteriously hours later when someone tries to log in.

**Important classes/functions:**

- `class Environment(enum.StrEnum)` — just two possible values: `development` or `production`.
  A simple way to ask "are we running for real, or just for testing/development?"
- `def to_asyncpg_url(url: str) -> str` — takes a database address and rewrites it slightly so
  SQLAlchemy's async engine understands it (cloud providers like Railway hand out addresses
  starting with `postgres://`, but the library needs `postgresql+asyncpg://`). This function
  exists in exactly one place so the rule is never duplicated or accidentally done differently in
  two places.
- `class Settings(BaseSettings)` — the actual list of every setting: database URL, JWT secret
  key, rate limits, AI settings (unused for now), file upload size limits, and more. Each one has
  a sensible default where possible.
- `_require_production_secrets()` — a special check that only runs when `ENVIRONMENT=production`.
  It demands that every external service credential (AI keys, cloud storage keys, error-tracking
  keys) actually be present. In development, these are all optional, so a developer's laptop
  doesn't need a full production setup just to run the code.
- `get_settings()` — the function every other file calls to actually read these settings. It's
  cached (`@lru_cache`) so the environment variables are only read and validated once, not on
  every single request.

**Real-world analogy:** think of this file as a pre-flight checklist a pilot runs before takeoff.
If any critical item is missing, the plane simply doesn't leave the ground — it doesn't take off
and then discover a problem mid-flight.

**Input:** environment variables (from a `.env` file locally, or from Railway's dashboard in
production).
**Output:** a validated `Settings` object every other file can safely read from.

**Depends on:** `pydantic` and `pydantic-settings` (for the validation magic).
**Depended on by:** almost everything — `app/db/session.py`, `app/core/security.py`,
`app/main.py`, and more.

---

### 5.2 `apps/api/app/core/money.py` — Money Handling

**Overall purpose:** this is one of the most important files in the whole project. It exists to
solve one specific, dangerous problem: **computers cannot represent most decimal fractions
exactly using the normal number type (`float`).** Try `0.1 + 0.2` in almost any programming
language and you'll get `0.30000000000000004`, not `0.3`. For everyday numbers that's a rounding
error nobody notices. For **money**, that kind of error compounding over thousands of
transactions could mean a shop's books don't balance and nobody can figure out why.

**How it solves this:** it uses Python's `Decimal` type everywhere instead of `float`, which can
represent money exactly. And it goes further — `parse_money()` will actively **refuse and raise
an error** if you try to pass it a `float` at all, rather than silently accepting one that might
already have lost precision.

**Important functions:**

- `parse_money(value)` — takes a string (like `"35000.00"`), an integer, or a `Decimal`, and
  turns it into a clean, rounded `Decimal`. Rejects empty strings, non-numeric text, `NaN`,
  infinity, and anything out of the database's allowed range.
- `quantize_money(value)` — rounds a `Decimal` to exactly 2 decimal places, using "round half
  up" (so `0.005` becomes `0.01`, matching how a human would round it by hand — this is
  deliberately different from Python's default rounding behavior, which rounds `0.5` to the
  nearest *even* number and would round `0.005` down to `0.00`).
- `format_money(value)` — turns a `Decimal` back into the exact string format used everywhere
  else in the system (always exactly 2 decimal places, e.g., `"35000.00"`, never a bare number).

**Real-world analogy:** imagine a cashier's calculator that physically refuses to let you type in
a number using the "wrong kind of button" for currency — even if you try, it stops you and asks
you to re-enter it the correct way.

**Input:** strings, ints, or `Decimal` values representing money.
**Output:** clean `Decimal` values, or text-based error messages if the input was invalid.

**Depends on:** nothing except Python's built-in `decimal` module.
**Depended on by:** currently, only its own tests (`tests/test_money_precision.py`). No business
logic uses money yet because no expense/salary/etc. recording code has been written.

---

### 5.3 `apps/api/app/core/dates.py` — Business Dates

**Overall purpose:** solves a real-world problem specific to running a shop: **what day did a
sale "happen" on, if the shop is still open past midnight?** If a shop closes at 11 PM and the
manager counts the cash drawer at 12:30 AM, that money belongs to *yesterday's* business day, not
today's — otherwise every day's numbers would be shifted and nothing would reconcile.

**Important functions:**

- `now_utc()` — returns the current moment in time, always in UTC (a single, unambiguous global
  time standard — everything the system stores uses this, and only converts to local time for
  display).
- `to_company_time(moment, tz)` — converts a UTC moment into the shop's local time zone
  (`Asia/Colombo` by default, which is UTC+5:30 all year round — Sri Lanka doesn't use daylight
  saving time, which simplifies this).
- `business_date_for(occurred_at, cutoff_hour, tz)` — the key function. It converts a moment to
  local time, and if the local hour is *before* the cutoff (2 AM by default), it returns
  **yesterday's** date instead of today's.

**Real-world analogy:** it's like how a 24-hour diner might count "Tuesday's sales" as everything
sold between opening Tuesday morning and 2 AM Wednesday — not everything sold on the literal
calendar date of Tuesday.

**Verified example (from the automated tests):** a sale at 12:30 AM local time (which is 19:00
UTC the previous day) correctly returns the **previous day's date**. A sale at exactly 2:00 AM
local time correctly returns the **new day's date**.

**Input:** a UTC timestamp, and optionally a custom cutoff hour or time zone.
**Output:** a plain calendar date (no time component).

**Depends on:** Python's built-in `datetime` and `zoneinfo` modules.
**Depended on by:** currently only its own tests. Will become critical once actual business
records (expenses, revenue, etc.) start being saved, since every record needs a `business_date`.

---

### 5.4 `apps/api/app/core/security.py` — Passwords and Tokens

**Overall purpose:** everything related to proving someone is who they say they are, and keeping
that proof secure. This file has two clear halves: password handling, and token
(login-session) handling.

**Password functions:**

- `hash_password(password)` — turns a plain-text password into an unreadable, scrambled string
  using **Argon2id** (currently considered one of the strongest password-hashing algorithms
  available). This scrambled version is what actually gets saved in the database — the real
  password is never stored anywhere.
- `verify_password(password, password_hash)` — checks if a plain-text password matches a stored
  hash, without ever needing to "unscramble" the hash (that's not even possible — hashing only
  goes one direction).
- `needs_rehash(password_hash)` — checks if an old password hash was created with weaker settings
  than we currently use, so it can be quietly upgraded next time that user logs in.
- `validate_password_strength(password)` — currently just enforces a 10-character minimum.

**Token functions:**

- `create_access_token(...)` — builds a **JWT** (JSON Web Token): a compact, digitally-signed
  piece of text that says "this is user X, with role Y, and this token expires at time Z." It's
  signed with a secret key so nobody can forge one or tamper with it undetected.
- `decode_access_token(token)` — checks a JWT's signature and expiry, and reads its contents back
  out. If the token is invalid or expired, this raises a `TokenError`.
- `generate_refresh_token()` — creates a long, random, hard-to-guess string (this is the *other*
  kind of token — a longer-lived one used to get a new access token without logging in again).
- `hash_refresh_token(token)` — hashes a refresh token with SHA-256 before it's stored in the
  database, so even someone with direct database access can't read out usable refresh tokens.

**Why two kinds of tokens?** The access token is short-lived (15 minutes) and is what's checked
on every request — if it leaked, the damage window is small. The refresh token lives much longer
(30 days) but is only used to quietly get a new access token, and it's device-specific (see
[Section 9](#9-authentication-and-security) for how stealing one is detected).

**Real-world analogy:** the access token is like a wristband at a one-day event — quick to check
at every door, but useless the next day. The refresh token is more like a season pass kept in
your wallet — you don't show it constantly, but you use it to get a fresh wristband each time you
show up.

**Depends on:** `argon2-cffi` (for hashing), `PyJWT` (for tokens), `app/config.py` (for the secret
key and settings).
**Depended on by:** `app/services/auth_service.py`, `app/dependencies/auth.py`.

---

### 5.5 `apps/api/app/core/errors.py` — Standardized Error Responses

**Overall purpose:** makes sure every error the server sends back to a client looks the same
shape, following a real internet standard called **RFC 9457 ("Problem Details")**. Instead of
one endpoint returning `{"error": "..."}` and another returning `{"message": "..."}`, everything
comes back looking like:

```json
{
  "type": "https://velmart.app/errors/invalid-credentials",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "Invalid email or password.",
  "code": "INVALID_CREDENTIALS",
  "request_id": "a1b2c3..."
}
```

**Important classes:**

- `class AppError(Exception)` — the base class every specific error inherits from. Carries an
  HTTP status code, a short machine-readable `code`, a human-readable `title`, and optionally
  extra data and HTTP headers.
- `class PermissionDeniedError`, `NotFoundError`, `ConflictError`, `ValidationFailedError` —
  ready-made specific error types for common situations.
- `register_exception_handlers(app)` — tells FastAPI "whenever any code raises an `AppError` (or
  a built-in HTTP error, or a validation error), catch it and format it using the standard shape
  above, instead of letting Python's default ugly error page show through."

**A subtle but important detail (and a bug that was caught and fixed here):** if a piece of code
wants to send back a special HTTP header (like `Retry-After`, telling a client how long to wait
before trying again), it must attach that header to the `AppError` exception itself
(`raise RateLimitedError(..., headers={"Retry-After": "30"})`). Setting it directly on FastAPI's
injected `Response` object does **not** work once an exception is raised — FastAPI builds an
entirely new response for the error, throwing away anything set on the old one. This file's
design specifically accounts for that.

**Depends on:** FastAPI's exception-handling tools.
**Depended on by:** `app/routers/auth.py`, `app/dependencies/auth.py`, and every future router.

---

### 5.6 `apps/api/app/core/logging.py` — Structured Logging

**Overall purpose:** every time something happens in the server (a request comes in, a login
fails, an error occurs), it should be recorded in a consistent, searchable format — as a single
line of JSON, not scattered plain-text sentences.

**Key details:**

- `configure_logging(level)` — sets up the whole logging system once, at startup.
- `_scrub(...)` — a "processor" that runs on **every single log line** and automatically replaces
  the value of any field named `password`, `token`, `access_token`, `refresh_token`, `token_hash`,
  `secret`, `api_key`, or `data` (a record's raw business values) with the text `[redacted]`.
  This is a safety net: even if a developer accidentally logs a whole object that happens to
  contain a password, it never actually reaches the log output in readable form.
- `bind_request_context(**kwargs)` / `clear_request_context()` — lets other code attach extra
  info (like "this log line belongs to request ID X, for user Y") that then automatically appears
  on every subsequent log line during that one request, without having to pass it around
  manually.

**Real-world analogy:** it's like a security guard's notebook that automatically blacks out any
sentence containing the word "password" before the ink even dries — no matter who's writing.

**Depends on:** the `structlog` library.
**Depended on by:** almost every file in the backend.

---

### 5.7 `apps/api/app/core/ratelimit.py` — Rate Limiting

**Overall purpose:** stops someone from rapidly guessing passwords (or otherwise hammering the
server) by counting how many requests come from the same source in a time window, and refusing
once a limit is hit.

**How it works:** every "bucket" (e.g., `login:ip:203.0.113.5`) gets a row in the `rate_limits`
database table for each one-minute window. Every request tries to insert-or-increment that row.
Because this uses a single atomic database statement (`INSERT ... ON CONFLICT ... DO UPDATE`),
two requests arriving at the exact same instant still can't both slip through thinking they're
"the 5th" — the database itself guarantees only one wins the race.

**Important functions:**

- `hit(...)` — the core counting function: increments a bucket and reports whether the caller is
  still under the limit.
- `hit_login_ip(session, ip_address)` — specifically checks the login rate limit (5 attempts per
  minute per IP address).
- `purge_expired(...)` — deletes old rate-limit windows so the table doesn't grow forever
  (intended to run nightly, though the actual nightly job doesn't exist as code yet).

**Real-world analogy:** it's like a bouncer with a tally counter — after 5 marks in one minute for
the same person, the door simply doesn't open again until the minute resets.

**Depends on:** the database, via SQLAlchemy.
**Depended on by:** `app/routers/auth.py` (the login endpoint).

---

### 5.8 `apps/api/app/core/idempotency.py` — Preventing Duplicate Actions

**Overall purpose:** solves the classic "I clicked submit twice because the page was slow" (or
"my phone lost signal and retried automatically") problem. If a client sends the exact same
request twice with the same unique "Idempotency-Key," the server recognizes it and returns the
**original** result instead of doing the action a second time.

**Important functions:**

- `hash_request(payload)` — creates a fingerprint of a request's contents, so the server can tell
  "is this literally the same request being replayed, or a different request that happens to
  reuse an old key by mistake?"
- `reserve(...)` — claims a key before starting work, so that if two identical requests arrive at
  the exact same moment, only one of them actually proceeds.
- `lookup(...)` — checks if a key has already been used, and returns the stored result if so.
  Raises a conflict error if the same key was used for a genuinely different request (a sign of a
  bug on the client side), or if a matching request is still in progress.
- `store_response(...)` — saves what actually happened, so a future replay can return it.
- `purge_expired(...)` — deletes idempotency records older than 48 hours (intended for a nightly
  job that doesn't exist as code yet).

**Real-world analogy:** it's like a bank teller who writes down a receipt number every time you
hand them a deposit slip. If you hand them the exact same slip again by accident, they just show
you the receipt from last time instead of depositing your money twice.

**Depends on:** the database.
**Depended on by:** currently, only its own tests. No endpoint uses this yet (the login endpoint
doesn't need idempotency; future endpoints for creating business records will).

---

### 5.9 `apps/api/app/db/base.py` — Shared Database Building Blocks

**Overall purpose:** rather than repeating the same handful of columns (`id`, `company_id`,
`created_at`, `version`, etc.) on every single database table's Python definition, this file
defines them once as reusable "mixins" that other model classes can combine.

**Important classes:**

- `class Base(DeclarativeBase)` — the root class every database table model inherits from.
- `class RecordStatus(enum.StrEnum)` — the three possible states a business record can be in:
  `ACTIVE`, `REVERSED`, or `VOID`.
- `class UUIDPKMixin` — adds an `id` column: a random, unique identifier (a UUID) that the
  database itself generates automatically for every new row.
- `class TenantMixin` — adds a `company_id` column, tying a row to a specific company (even
  though today there's only ever one company, this is built in from day one so scaling to
  multiple companies later is a data change, not a rewrite).
- `class TimestampMixin` — adds `created_at` and `updated_at` columns, automatically filled in by
  the database.
- `class VersionMixin` — adds a `version` number, starting at 1 and meant to be incremented on
  every change — this is how the (future) system will detect "someone else already changed this
  since you last looked at it" conflicts.
- `class BusinessTableMixin` — combines all of the above, plus several more columns
  (`store_id`, `occurred_at`, `business_date`, `status`, `needs_review`, `created_by`,
  `updated_by`, `source`, `client_uuid`, `import_batch_id`, `is_deleted`, `deleted_reason`) that
  every future business record table (expenses, salaries, etc.) will share.

**Real-world analogy:** imagine a form-design template that already has "Name," "Date," and
"Signature" boxes pre-printed on it — every new form the company creates starts from that
template instead of someone redrawing those same three boxes from scratch every time.

**Depends on:** SQLAlchemy.
**Depended on by:** almost every file in `app/models/`.

---

### 5.10 `apps/api/app/db/session.py`, `readonly.py`, `rls.py` — Database Connections

These three files set up **how** the application actually talks to PostgreSQL.

- **`session.py`** creates the main, read-write database connection (used for almost everything).
  It's built once and reused (`@lru_cache`) rather than reconnecting on every request, which would
  be slow. `get_session()` is the function FastAPI calls to hand a fresh database session to any
  endpoint that needs one.

- **`readonly.py`** creates a **separate** connection specifically reserved for the future AI
  assistant's read-only access. It deliberately uses a different database login (`ai_reader`) that
  has no write permission at all — this file exists so that even if a bug were introduced in the
  AI code later, it would be *architecturally impossible* for it to accidentally write to the
  database, because the connection it's using simply doesn't have that permission. Not used by any
  code yet — it's set up in advance of the AI feature being built.

- **`rls.py`** contains `set_rls_context()` — the function that tells PostgreSQL "for the rest of
  this transaction, treat me as belonging to company X, with role Y, and access to these stores."
  This has to be called *inside* an open transaction, or PostgreSQL's security rules would
  otherwise hide every row from the query (since the database wouldn't know which company to show
  data for). It deliberately uses PostgreSQL's `set_config()` function with a proper parameter
  instead of building a raw SQL string — this matters because building SQL by joining text
  together is exactly how "SQL injection" security holes happen, and this file avoids that
  category of bug entirely by construction.

**Real-world analogy:** `session.py` is the main door everyone uses. `readonly.py` is a separate
side door that physically cannot be used to carry anything *out* of the building, only to look
around. `rls.py` is like showing your ID badge to a guard the moment you walk in, so every door
after that automatically knows which floors you're allowed on.

---

### 5.11 `apps/api/app/dependencies/auth.py` — "Is This a Valid Logged-In User?"

**Overall purpose:** a single, reusable check that any endpoint can require. Currently used by
the `/me` endpoint, and it will be reused by every future endpoint that needs someone to be
logged in.

**How it works (`current_user`):**

1. Looks for an `Authorization: Bearer <token>` header on the incoming request.
2. If missing, immediately fails with "not authenticated."
3. Decodes and verifies the JWT (using `security.py`'s `decode_access_token`).
4. Looks up the actual user in the database by the ID inside the token.
5. Checks the user is still active.
6. **Crucially**, compares the `token_version` number stored in the token against the
   `token_version` number currently stored on the user's database row. If they don't match, the
   token is rejected — **even if it hasn't technically expired yet.**

**Why step 6 matters so much:** it's what makes it possible to instantly invalidate every session
a user has, the moment something important changes (their password is reset, their role changes,
or their account is deactivated) — by simply incrementing one number in the database. Every token
issued before that moment becomes worthless immediately, without needing to track down and
individually cancel each one.

**Real-world analogy:** imagine every ID badge printed with a small version number on it, and the
front desk keeps a master list of "the current valid version number" per person. If IT ever needs
to instantly revoke someone's access, they just bump that one number — every badge with an older
number now gets rejected at every door, no matter how many badges were printed.

**Depends on:** `app/core/security.py`, `app/db/session.py`, `app/models/user.py`.
**Depended on by:** `app/routers/auth.py`'s `/me` endpoint (currently the only place this is
used).

---

### 5.12 `apps/api/app/services/auth_service.py` — The Actual Login Logic

**Overall purpose:** this is where all the real decision-making for login, refresh, and logout
happens. Routers (in `app/routers/auth.py`) are deliberately kept "thin" — they just receive the
HTTP request and hand off to this file for the actual work.

**Important functions:**

- `login(...)` — the full login process: find the user, check lockout status, verify the
  password, handle failure (increment counter, maybe lock the account, write an audit-log entry),
  or handle success (reset the counter, issue new tokens, write an audit-log entry).
- `refresh(...)` — the full token-refresh process, including detecting and reacting to **token
  reuse** (explained in detail in [Section 9](#9-authentication-and-security)).
- `logout(...)` — revokes the presented refresh token. Deliberately does nothing if the token
  wasn't found — logging out twice, or with a token that's already gone, isn't an error.
- `store_ids_for(session, user)` — figures out which physical shop locations ("stores") a user
  can see records for. Owners can see every store automatically; managers only see stores they've
  been explicitly assigned to.

**A genuinely important bug that was found and fixed while building this file:** the very first
version of this code assumed the *router* would wrap each of these functions in a database
transaction (`async with session.begin(): ...`). But when a function like `login()` fails (wrong
password) and *raises an exception* partway through, wrapping it that way meant the transaction
automatically rolled back — silently undoing the "increment the failed-attempt counter" update
and the "write an audit-log entry" that had just happened, **and, far more seriously, undoing the
"revoke every token for this device" action that runs when a stolen refresh token is detected
being reused.** In other words, the original code would have correctly *detected* a stolen token
being replayed, decided to revoke the whole device — and then thrown that decision away right
before telling the caller "access denied," leaving the stolen token family still valid. This was
only caught because the automated tests run against a **real database** rather than a fake one,
and a test specifically checked "after a detected replay, is the token family actually revoked in
the database?" The fix: every function in this file now explicitly commits its own database
changes *before* raising any error, so the important side effects always survive regardless of
what the caller does afterward.

**Depends on:** `app/core/security.py`, `app/db/rls.py`, `app/models/user.py`.
**Depended on by:** `app/routers/auth.py`.

---

### 5.13 `apps/api/app/routers/auth.py` — The Auth HTTP Endpoints

**Overall purpose:** defines the actual URLs a client can call: `/auth/login`, `/auth/refresh`,
`/auth/logout`, and `/me`. Translates between "HTTP request/response" and "call the service layer
and turn the result into JSON." See [Section 7](#7-apis-and-endpoints) for the full endpoint
documentation.

**Depends on:** `app/services/auth_service.py`, `app/core/ratelimit.py`,
`app/dependencies/auth.py`, `app/schemas/auth.py`.
**Depended on by:** `app/main.py`, which registers this router onto the app.

---

### 5.14 `apps/api/app/routers/health.py` — Health Checks

**Overall purpose:** two simple endpoints used to answer the question "is the server actually
working right now?" — important for automated deployment systems (like Railway) that need to know
whether it's safe to send real traffic to a newly-started server.

- **`GET /health`** — the simplest possible check: "is the process even running?" Always returns
  `{"status": "ok"}` if the server can respond at all.
- **`GET /health/ready`** — a deeper check: can it actually reach the database, **and** has that
  database had all its migrations applied? It does this by comparing the database's current
  migration version against what this specific build of the code expects. If they don't match
  (e.g., the code was updated but `alembic upgrade head` hasn't run yet), it returns a `503`
  ("service unavailable") instead of `200`. This is deliberately what stops a broken deployment
  from ever receiving real traffic.

**Real-world analogy:** `/health` is like knocking on a door and hearing "I'm here!" `/health/ready`
is like also asking "and do you actually have today's delivery ready to go?"

**Depends on:** `app/db/session.py`, the Alembic migration files (to know the "expected" version).
**Depended on by:** nobody in code — it's meant to be called by external monitoring tools and by
Railway's own deployment system.

---

### 5.15 `apps/api/app/schemas/auth.py` — Request/Response Shapes

**Overall purpose:** defines, using Pydantic, the *exact* shape of data going in and out of the
auth endpoints. FastAPI uses these definitions to automatically validate incoming JSON (rejecting
malformed requests before any of our code even runs) and to automatically generate the correct
JSON shape for responses.

- `LoginRequest` — `email` (must look like a real email address), `password`, `device_id`, and an
  optional `device_name`.
- `RefreshRequest`, `LogoutRequest` — both just carry a `refresh_token` string.
- `UserOut` — the safe, public-facing shape of a user: id, company, name, email, role, and the
  list of stores they can access. Notably, this **never** includes the password hash — that field
  simply isn't listed here, so it's structurally impossible for it to leak out through this
  endpoint.
- `TokenResponse` — what gets sent back after a successful login or refresh: the access token, its
  type (`"bearer"`), how many seconds until it expires, the refresh token, and the user info.

**Depends on:** Pydantic.
**Depended on by:** `app/routers/auth.py`.

---

### 5.16 `apps/api/app/main.py` — Tying Everything Together

**Overall purpose:** this is the file that actually builds the running FastAPI application.

**What it does, step by step:**

1. Reads settings (which validates them, crashing early if something's wrong).
2. Sets up structured logging.
3. If a Sentry error-tracking key is configured, activates Sentry (currently inactive since no
   key exists).
4. Creates the FastAPI app itself — disabling the interactive API documentation page (`/docs`)
   when running in production, since it shouldn't be publicly browsable in a live system.
5. Adds a custom "middleware" (code that runs on every single request) that:
   - generates or reuses a unique `X-Request-ID` for tracing one request through the logs,
   - times how long the request took,
   - logs a line when the request completes (skipping the noisy `/health` endpoint, which gets
     polled every minute by monitoring tools),
   - logs a full error trace if anything crashed.
6. Registers the error-handling logic from `errors.py`.
7. Registers the two routers that exist (`health`, `auth`).
8. On shutdown, cleanly closes the database connections.

**Real-world analogy:** this file is like the general manager who unlocks the building each
morning, checks the lights and alarms work, puts a sign-in sheet at the front desk (the request
ID), and makes sure every department (each router) actually has an office to work from.

**Depends on:** almost everything else in `app/`.
**Depended on by:** it's the actual entry point — `uvicorn app.main:app` runs this file.

---

### 5.17 `apps/api/app/models/*.py` — Database Table Definitions

There are 27 files describing 27 database tables (plus a few enums). Because they're described in
full, table-by-table, in [Section 8 (Database)](#8-database), they're only briefly summarized
here by group:

| File(s) | Tables described |
|---|---|
| `company.py` | `companies`, `company_settings` |
| `store.py` | `stores` |
| `user.py` | `users`, `user_stores`, `refresh_tokens`, `idempotency_keys` |
| `rate_limit.py` | `rate_limits` |
| `page.py`, `page_column.py`, `page_validation.py`, `page_access.py` | `pages`, `page_columns`, `page_validations`, `page_access` (the future "custom table builder" feature) |
| `record.py` | `records` (where business data would live, for Owner-created pages) |
| `attachment.py`, `import_batch.py` | `attachments`, `import_batches` (future file uploads and CSV imports) |
| `dashboard_widget.py` | `dashboard_widgets` (future dashboard configuration) |
| `audit.py` | `audit_logs` (the tamper-proof history log) |
| `ai.py` | `ai_sessions`, `ai_messages`, `ai_proposals`, `ai_proposal_items` (future AI assistant) |
| `business/employee_salary.py`, `purchases.py`, `expenses.py`, `daily_revenue.py`, `cash_ledger.py`, `cheques.py` | The six core business tables this shop actually needs |
| `business/__init__.py` | Two important lookup lists: which page names map to which tables, and which page names are "reserved" so an owner can't accidentally create a duplicate, conflicting table |
| `__init__.py` | Imports every single model file, so SQLAlchemy and Alembic know about all of them |

**Important:** these files define the database *structure* in Python. **None of them yet have any
service or router code that actually reads or writes to most of these tables** (except `users`,
`refresh_tokens`, `idempotency_keys`, and `rate_limits`, which the working auth system uses). The
tables physically exist in the database (created by the migrations), and the Python classes that
describe their shape exist, but there's no business logic wired up to use the rest yet.

---

### 5.18 The Nine Database Migrations (`apps/api/alembic/versions/`)

Covered fully in [Section 8](#8-database). In short: these are the files that actually created
every table, security rule, and the audit trail's tamper-detection trigger inside PostgreSQL.

---

### 5.19 The Automated Tests (`apps/api/tests/`)

| File | What it tests |
|---|---|
| `conftest.py` | Not a test itself — shared setup that every other test file uses. Spins up a real, temporary PostgreSQL 18 database (using `testcontainers`), runs every migration against it, and provides reusable helpers (a test company, a test "owner" user, an HTTP client wired to the app) |
| `test_money_precision.py` | Proves `money.py` never loses precision, always rejects floats, and rounds correctly |
| `test_business_dates.py` | Proves the midnight cash-up rule works correctly at, before, and after the cutoff hour |
| `test_auth_login.py` | Proves login works, wrong passwords are rejected generically (indistinguishable from an unknown email), the account locks after 5 failures, and failures are recorded in the audit log |
| `test_auth_refresh.py` | Proves refresh tokens rotate correctly, and that replaying an already-used token correctly revokes the whole device's tokens |
| `test_token_version.py` | Proves that bumping a user's `token_version` immediately invalidates their existing, still-unexpired access token |
| `test_rate_limit.py` | Proves the login rate limiter actually blocks a 6th attempt within one minute |
| `test_idempotency.py` | Proves duplicate requests with the same key are recognized, and conflicting requests with a reused key are rejected |

**Total: 81 tests, all passing**, run against a genuinely real database every time (never a fake
one) — this was a deliberate choice specifically because a fake/mocked database would have hidden
the transaction-rollback bug described in Section 5.12.

---

### 5.20 The Mobile Client Files (`apps/mobile/lib/`)

**Important overall caveat repeated from Section 1:** every file below was written carefully, but
**none of it has ever actually been compiled or run**, because Flutter is not yet fully installed
and set up on the development machine. Two real bugs were found and fixed purely by careful manual
reading of the code (not by a compiler) — this is mentioned again here because it's an important
limitation to remember when reading this section.

- **`lib/core/money/money.dart`** — the Dart equivalent of `money.py`. Instead of `Decimal`
  (which Python has built in), it stores money as a plain integer count of "cents" (called
  "minor units" in the code), because Dart's `double` has the exact same floating-point precision
  problem Python's does. `Money.parse("35000.50")` turns a wire-format string into
  `3500050` (cents) internally; `.toApiString()` turns it back into `"35000.50"` for sending to
  the server; `.format()` produces a nice display string like `"Rs. 35,000.50"`. Has a full test
  file (`test/core/money_test.dart`) mirroring the Python tests.

- **`lib/core/storage/secure_store.dart`** — wraps the `flutter_secure_storage` package to save
  and read the access token, refresh token, and a generated device ID from the operating system's
  encrypted vault (Keychain on Apple devices, Keystore on Android).

- **`lib/core/network/api_client.dart`** — builds one shared `Dio` HTTP client instance,
  pointed at the server address from `env.dart`, with the two interceptors below attached.

- **`lib/core/network/auth_interceptor.dart`** — automatically attaches
  `Authorization: Bearer <token>` to every outgoing request (except login/refresh themselves).
  If a request comes back with a `401 Unauthorized`, it automatically tries to refresh the token
  *once* and retries the original request — the user never sees this happen. Carefully written so
  that if five requests all fail with 401 at the exact same moment, only **one** refresh call is
  actually made (they all share the same in-progress attempt) — this matters because the server
  treats a *second* refresh attempt using an already-used token as a sign of theft (see
  [Section 9](#9-authentication-and-security)), so accidentally firing multiple refreshes at once
  could trigger a false "this device is compromised" response.

- **`lib/core/network/retry_interceptor.dart`** — automatically retries requests that failed due
  to a network problem (timeout, connection error, or server error), using increasing delays
  between attempts. Only retries write requests (`POST`, etc.) if they carry an
  `Idempotency-Key` header, since blindly retrying a write that might have partially succeeded
  could otherwise create a duplicate.

- **`lib/features/auth/domain/user.dart`** — a plain data class representing a logged-in user
  (id, company, name, email, role, store list), matching the shape the server sends back.

- **`lib/features/auth/data/auth_repository.dart`** — the Dart equivalent of the server's
  `auth_service.py`: the actual functions that call `/auth/login`, `/me`, and `/auth/logout`, and
  save/clear tokens in the secure store as needed.

- **`lib/features/auth/application/auth_controller.dart`** — manages the app's current
  authentication *state* (checking / authenticated / unauthenticated) using Riverpod, so any
  screen can react to "the user just logged in" or "the user just logged out" automatically.

- **`lib/features/auth/presentation/login_screen.dart`**, **`home_screen.dart`** — the two actual
  visual screens: a form with email/password fields and a "Sign in" button, and a simple screen
  showing the logged-in user's name and role with a sign-out button.

- **`lib/routing/guards.dart`**, **`app_router.dart`** — decide which screen to show based on the
  current authentication state, automatically redirecting an unauthenticated user to the login
  screen and an authenticated one away from it. Explicitly documented in the code as a **UI
  convenience only** — it never makes an actual security decision; that's the server's job alone.

---

## 6. Important Code Flows

Only one complete flow currently exists end-to-end. It's described in detail in
[Section 3](#3-system-architecture) above. To avoid repeating it, here is the same flow broken
into the exact function calls involved, for anyone who wants to trace it in the actual code:

```
User taps "Sign in"
  → login_screen.dart: _submit()
    → auth_controller.dart: AuthController.login()
      → auth_repository.dart: AuthRepository.login()
        → (Dio sends POST /auth/login)
          → app/routers/auth.py: login()
            → app/core/ratelimit.py: hit_login_ip()   [check: not too many attempts]
            → app/services/auth_service.py: login()
              → looks up User by email (SQLAlchemy query)
              → app/core/security.py: verify_password()
              → (on failure) updates failed_attempts, writes audit_logs row, commits, raises
              → (on success) issues new access + refresh tokens, writes audit_logs row, commits
            → builds TokenResponse
          ← (JSON response sent back)
        ← saves tokens via secure_store.dart: SecureStore.saveTokens()
      ← updates AuthState to "authenticated"
    ← go_router notices the state change and redirects to home_screen.dart
```

The **refresh** flow (when an access token expires) works similarly but is triggered
automatically by `auth_interceptor.dart` whenever any request gets a `401` response, rather than
by a user action — the person using the app never sees this happen.

Every other flow described in the project plan (recording an expense, viewing a dashboard, asking
the AI a question, importing a CSV file) **does not exist in code yet.**

---

## 7. APIs and Endpoints

Every endpoint that currently exists and does something real:

### `GET /health`

- **Purpose:** liveness check — "is the process running at all?"
- **Auth required:** none (public)
- **Request:** no parameters
- **Response:** `{"status": "ok"}`, always `200 OK` if the server can respond at all
- **Handled by:** `app/routers/health.py`
- **Talks to:** nothing else — doesn't even touch the database

### `GET /health/ready`

- **Purpose:** readiness check — "is the database reachable, and are migrations up to date?"
- **Auth required:** none (public)
- **Request:** no parameters
- **Response:** `{"status": "ready", "checks": {"database": true, "migrations": true}}` on
  success (`200`), or `{"status": "not_ready", "checks": {...}}` with a `503` status if either
  check fails
- **Handled by:** `app/routers/health.py`
- **Talks to:** PostgreSQL (a simple `SELECT 1` and a check of the `alembic_version` table)

### `POST /auth/login`

- **Purpose:** log a user in with email + password, get back an access token and refresh token
- **Auth required:** none (this is how you *get* authenticated)
- **Request body:** `{"email": "...", "password": "...", "device_id": "...", "device_name": "..." (optional)}`
- **Processing:** rate-limit check → look up user → verify password → check lockout → issue
  tokens or record failure
- **Response (success, `200`):** `{"access_token": "...", "token_type": "bearer", "expires_in": 900, "refresh_token": "...", "user": {...}}`
- **Response (failure, `401`):** a standard problem-details error with `code: "INVALID_CREDENTIALS"`
- **Response (too many attempts, `429`):** a problem-details error with a `Retry-After` header
- **Handled by:** `app/routers/auth.py` → `app/services/auth_service.py`
- **Talks to:** the `users`, `refresh_tokens`, and `audit_logs` tables, plus `rate_limits`

### `POST /auth/refresh`

- **Purpose:** trade a still-valid refresh token for a brand new access + refresh token pair,
  without needing the password again
- **Auth required:** a valid refresh token in the request body (not a bearer header)
- **Request body:** `{"refresh_token": "..."}`
- **Response (success, `200`):** same shape as login
- **Response (failure, `401`):** if the token is unknown, expired, or (importantly) already used
  once before — see [Section 9](#9-authentication-and-security) for what happens in that last case
- **Handled by:** `app/routers/auth.py` → `app/services/auth_service.py`
- **Talks to:** the `refresh_tokens`, `users`, and `audit_logs` tables

### `POST /auth/logout`

- **Purpose:** invalidate a specific refresh token (typically called when a user taps "sign out")
- **Auth required:** the refresh token itself is the proof
- **Request body:** `{"refresh_token": "..."}`
- **Response:** `204 No Content` (empty body) — always, even if the token was already invalid or
  unknown (logging out twice isn't an error)
- **Handled by:** `app/routers/auth.py` → `app/services/auth_service.py`
- **Talks to:** the `refresh_tokens` table

### `GET /me`

- **Purpose:** "who am I, according to my current access token?" — used by the client to display
  the logged-in user's name and role, and by anything that needs to double-check the current
  session is still valid
- **Auth required:** a valid `Authorization: Bearer <access_token>` header
- **Request:** no body
- **Response (success, `200`):** `{"id": "...", "company_id": "...", "full_name": "...", "email": "...", "role": "OWNER" or "MANAGER", "store_ids": [...]}`
- **Response (failure, `401`):** if the token is missing, invalid, expired, or its `token_version`
  no longer matches the database
- **Handled by:** `app/routers/auth.py` → `app/dependencies/auth.py` (for the auth check) →
  `app/services/auth_service.py` (for the store list)
- **Talks to:** the `users`, `stores`, and `user_stores` tables

**Every other endpoint described in `docs/API.md`** (pages, records, attachments, CSV import,
dashboard, audit log, AI) **does not exist in code.** Those router files (e.g.,
`app/routers/pages.py`, `app/routers/records.py`) are currently empty placeholder files.

---

## 8. Database

### Database technology

**PostgreSQL 18**, run locally via Docker (`infra/docker-compose.yml`). The application talks to
it using SQLAlchemy's async engine with the `asyncpg` driver underneath.

### How the application connects

There are (or will be) **three separate database logins**, each with different permissions —
following the security principle of "give every piece of code only the access it actually needs":

| Role | Used for | Permissions |
|---|---|---|
| `app_user` | The main application (everything today) | Can read and write almost every table, but is specifically forbidden from updating, deleting, or emptying the `audit_logs` table |
| `ai_reader` | The future AI assistant's read-only access | Can only `SELECT` (read) data; cannot see the `users`, `refresh_tokens`, or `idempotency_keys` tables at all; every query it runs has an 8-second time limit |
| `migrator` | Applying database migrations | Used only by Alembic when running `alembic upgrade head` |

Only `app_user` is actually used by working code today. The other two roles exist in the database
(created by the migrations) and have a Python file ready to connect through them
(`app/db/readonly.py` for `ai_reader`), but nothing uses them yet.

### The migrations, in order

Each migration is a numbered Python file that describes a change to the database, plus how to
undo it. Running `alembic upgrade head` applies every migration in order, from the very beginning
up to the latest.

| Migration | What it created |
|---|---|
| `0001_tenancy_and_users` | The `companies`, `company_settings`, `stores`, `users`, `user_stores`, `refresh_tokens`, and `idempotency_keys` tables, plus the three database roles listed above |
| `0002_page_engine` | The `pages`, `page_columns`, `page_validations`, `page_access`, and `records` tables — the foundation for the future "Owner builds their own custom table" feature |
| `0003_attachments_imports` | The `attachments` and `import_batches` tables — for future file uploads and CSV imports |
| `0004_dashboard_widgets` | The `dashboard_widgets` table — for a future configurable dashboard |
| `0005_audit_trigger_hashchain` | The `audit_logs` table, plus a special PostgreSQL trigger that makes it tamper-evident (explained below) |
| `0006_rls_policies` | Turns on Row-Level Security and adds the actual security rules for most tables |
| `0007_ai_tables` | The `ai_sessions`, `ai_messages`, `ai_proposals`, and `ai_proposal_items` tables, for the future AI feature |
| `0008_business_tables` | The six real business tables this shop needs: `employee_salaries`, `purchases`, `expenses`, `daily_revenue`, `cash_ledger`, `cheques` — plus a database *view* called `daily_reconciliation` that automatically compares the day's recorded revenue against the counted cash |
| `0009_rate_limits` | The `rate_limits` table used by the login rate limiter |

### The full table list (27 tables + 1 view)

**Tables actually used by working code today:**

- `companies` — one row per shop (currently, always exactly one row)
- `users` — every person who can log in, with their role (`OWNER` or `MANAGER`), their password
  hash, and lockout-tracking columns (`failed_attempts`, `locked_until`)
- `user_stores` — which shop locations ("stores") each manager can see
- `refresh_tokens` — every issued refresh token (as a hash, never the real value), including
  which device it belongs to and whether it's been revoked
- `idempotency_keys` — records of recent "don't repeat this action twice" requests
- `rate_limits` — counters used to enforce the login rate limit
- `audit_logs` — the permanent, tamper-evident history log

**Tables that exist (created by migrations) but have no code using them yet:**

- `company_settings`, `stores` (beyond the login flow reading them), `pages`, `page_columns`,
  `page_validations`, `page_access`, `records`, `attachments`, `import_batches`,
  `dashboard_widgets`, `ai_sessions`, `ai_messages`, `ai_proposals`, `ai_proposal_items`,
  `employee_salaries`, `purchases`, `expenses`, `daily_revenue`, `cash_ledger`, `cheques`

**A view (not a table — a saved query that always shows fresh results):**

- `daily_reconciliation` — for any given day, automatically compares the total revenue recorded
  in `daily_revenue` against the total counted cash in `cash_ledger`, and shows the difference. A
  difference of zero means the books balance for that day. **No code reads from this view yet.**

### The audit trail — how it can't be tampered with

This is one of the more clever pieces of the database design, so it deserves a plain-language
explanation.

**The problem:** a normal log/history table can be edited or deleted by anyone with database
access — including a bug in the application itself, or someone with stolen database credentials.
That defeats the whole purpose of a permanent record.

**The solution, in three parts:**

1. **A PostgreSQL trigger** (a small program the database itself runs automatically) computes a
   "hash" (a unique fingerprint) for every new audit log entry, based on that entry's contents
   *plus* the hash of the entry right before it — like each link in a chain being welded to the
   one before it. If anyone ever tampered with an old entry, its hash would no longer match, and
   every entry after it in the chain would become detectably inconsistent.
2. **The database itself is told: "the application's normal login (`app_user`) is not allowed to
   UPDATE, DELETE, or TRUNCATE (empty) this table."** This isn't a rule enforced by the
   application code that a bug could bypass — it's enforced by PostgreSQL itself, at the
   permission level.
3. **A planned nightly job** (not yet built) would walk the whole chain and confirm every link
   still matches, alerting if anything's broken.

**A subtle bug that was found and fixed while building this:** the very first version of the
trigger needed to briefly lock the *previous* row while computing the next hash, to stop two
audit entries being written at the exact same instant from both trying to chain onto the same
"previous" entry. But locking a row for this purpose requires the *UPDATE* permission in
PostgreSQL — even though nothing is actually being updated — which directly conflicted with rule
#2 above (`app_user` isn't allowed to update this table). The fix: the trigger function itself
runs with special elevated permissions (as its own trusted "owner," not as whoever triggered it),
so the locking works internally, while `app_user` still can never issue a *direct* update or
delete against the table from application code. This was caught by actually running the code
against a real, permission-locked PostgreSQL database — a fake/mocked database would never have
revealed this, since it wouldn't have enforced real permissions at all.

### Row-Level Security (RLS) — the second line of defense

Beyond the application code checking "does this user belong to this company," PostgreSQL itself
is configured to enforce the same rule, automatically, on every single query — even one written
by a future developer who forgot to add that check. If the application ever tries to read or
write a row belonging to a different company, the database silently returns nothing, rather than
leaking it.

This was specifically verified during development by connecting to the database *as* the
`app_user` role (not as an all-powerful superuser) and confirming: a query for "Company A's data"
while set to "Company A" context correctly returns rows, and the same query while set to
"Company B" context correctly returns zero rows — even without changing anything else about the
query itself.

### ORM — how Python code describes tables

Every table has a matching Python class in `app/models/`, using SQLAlchemy's modern style (e.g.,
`Mapped[str]`, `mapped_column(...)`). This means Python code can write
`session.execute(select(User).where(User.email == email))` instead of writing raw SQL text
everywhere — though a few places (especially in `auth_service.py`, for things like the audit log
insert, which needs to set the special RLS context first) intentionally use raw SQL via
`sqlalchemy.text()`, because that specific job needs more direct control than the ORM easily
provides.

---

## 9. Authentication and Security

### Login flow

Already described in detail in [Sections 3](#3-system-architecture) and
[6](#6-important-code-flows). In short: email + password → Argon2id verification → JWT access
token + random refresh token issued → both handed to the client → client stores them securely.

### Password handling

- Passwords are **never stored in plain text**, anywhere, ever.
- They're hashed with **Argon2id**, using deliberately expensive settings (64 MB of memory, 3
  passes, 4 parallel threads) specifically chosen to make large-scale password-guessing attacks
  slow and expensive, even if someone got a copy of the database.
- Minimum password length: 10 characters.
- If a stored hash was created with older/weaker settings than the current ones, it's
  automatically re-hashed (upgraded) the next time that person logs in successfully.

### Authorization / roles

Exactly two roles exist in the system design: **`OWNER`** and **`MANAGER`**. Today, the *only*
place a role actually matters in working code is that it's included in the `/me` response and
in the access token itself. **No endpoint currently checks "is this user an owner?" before
allowing an action** — that permission-checking system (`app/core/permissions.py`) is planned but
is currently an empty file. So right now, any successfully logged-in user (owner or manager)
could theoretically call any endpoint that exists — but since only the auth endpoints exist at
all, there's nothing sensitive to protect yet.

### Tokens — the two-token system, and how token theft is detected

- **Access token:** a JWT, valid for 15 minutes, sent with every request as
  `Authorization: Bearer <token>`. Contains the user's ID, company, role, store list, and a
  `token_version` number.
- **Refresh token:** a long random string, valid for 30 days, tied to a specific device. Used
  only to get a new access token without re-entering a password.

**The theft-detection trick:** every time a refresh token is used, it's immediately marked
"revoked" and a brand new one is issued in its place (this is called **rotation**). If the *same*
already-revoked refresh token is ever presented again, the server assumes it must have been
stolen and copied somewhere — because in normal use, nobody would ever present an old, already-
replaced token. When this is detected, **every single refresh token belonging to that device is
immediately revoked**, forcing a fresh login on that device. This event is also written
permanently to the audit log.

### Instant session invalidation

Every user has a `token_version` number, starting at 1. Every access token carries the version
number it was issued with. If that number is ever bumped in the database (which would happen on
a password change, a role change, or an account being deactivated — though no code currently
triggers this automatically yet), **every previously issued access token instantly stops working**,
even ones that haven't technically expired — because the check in `app/dependencies/auth.py`
compares the token's version against the *current* database value on every single request.

### Environment variables / secrets

All secret configuration (database passwords, the JWT signing key, future API keys) lives in
environment variables, documented — with placeholder, non-real values — in
`apps/api/.env.example`. The actual `.env` file with real values is explicitly excluded from Git
via `.gitignore`, so secrets never get committed to the repository.

### Network / security configuration

- The server currently sets **no CORS policy** — meaning it's not designed to be called directly
  from a web browser's JavaScript. This is intentional: the plan has no web app in version 1, only
  native mobile/desktop clients.
- The interactive API documentation page (`/docs`) is automatically disabled when
  `ENVIRONMENT=production`.
- Every error response includes a `request_id`, making it possible to trace exactly what happened
  for one specific request through the logs, without exposing any internal detail to the client
  itself.

### What is *not* yet implemented, security-wise

- No permission-matrix system (the plan's central rule of "every action is checked against a
  matrix of role × endpoint" doesn't exist as code).
- No two-factor authentication.
- No rate limiting on anything except the login endpoint.
- No account lockout notifications or alerts.

---

## 10. Deployment and Infrastructure

### What's working today

- **Docker + Docker Compose:** running `docker compose -f infra/docker-compose.yml up -d postgres`
  starts a real PostgreSQL 18 database on your own computer, matching the exact version the
  production system is meant to use. This has been tested extensively, including a real bug fix
  (PostgreSQL 18's Docker image changed how it expects its data folder to be organized compared to
  older versions — the `docker-compose.yml` file had to be corrected for this).
- **Local development server:** `uv run uvicorn app.main:app --reload` runs the actual backend
  server on your own machine, talking to that local database.
- **GitHub Actions CI:** every time code is pushed to GitHub, `api-ci.yml` automatically installs
  everything, checks code style, checks types, and runs all 81 tests against a real, freshly-
  created PostgreSQL database. `mobile-ci.yml` does the equivalent for the Dart code (installing a
  real Flutter SDK on GitHub's own servers, since Flutter isn't fully set up locally yet).

### What's configured but not yet live

- **`infra/railway.json`** — a configuration file describing exactly how the backend should be
  deployed to Railway (a cloud hosting service): which Docker file to use, what command starts the
  server, how to check if it's healthy, and how many copies to run. **No actual Railway account or
  project has been created**, so this file currently does nothing — it's ready for the moment
  someone sets that up.
- **`deploy-production.yml`** — the GitHub Actions workflow that *would* automatically deploy to
  Railway after tests pass. It deliberately checks for a secret called `RAILWAY_TOKEN` first, and
  if that secret doesn't exist (which it currently doesn't), it skips itself entirely rather than
  failing loudly on every single push.

### What's deferred / not started at all

- Any live, publicly-reachable version of this application.
- Backup and disaster-recovery scripts (`infra/scripts/backup_dump.sh`, `restore_drill.sh` exist
  only as empty files).
- A staging environment (the plan explicitly says: add one only once it's actually needed).
- Object/file storage (for attachments) — no cloud storage bucket has been set up.

### Development vs. production environments

The `Environment` setting (`development` or `production`) changes real behavior today:

| Setting | Development | Production |
|---|---|---|
| `/docs` (API documentation page) | Enabled | Disabled |
| AI, cloud storage, error-tracking credentials | Optional | Required — server refuses to start without them |

---

## 11. Current Project Status

| Component | Status | What has been completed | What remains |
|---|---|---|---|
| Database schema | ✅ Done, verified | All 27 tables, 3 database roles, Row-Level Security, tamper-evident audit trail — all tested against a real PostgreSQL 18 database, including deliberately triggering and confirming several security properties | Nothing — this piece is solid for what's been designed so far |
| User login / logout / refresh | ✅ Done, verified | Full flow with lockout, rate limiting, token rotation, theft detection, and audit logging — 81 automated tests pass | Password reset flow, two-factor authentication, "log out of all devices" |
| Money & date handling | ✅ Done, verified | Both backend (Python) and client (Dart) versions exist and are tested | Nothing new needed until real business records start being built |
| Permission system (roles) | ⛔ Not started | The two roles exist as a concept and are stored on each user | No code anywhere actually checks "is this action allowed for this role" |
| Business record features (expenses, salaries, purchases, revenue, cheques) | ⛔ Not started | Database tables exist | No backend service code, no API endpoints, no mobile screens |
| The "page engine" (Owner-built custom tables) | ⛔ Not started | Database tables exist | Everything else |
| AI assistant | ⛔ Not started | Database tables exist | Everything else |
| CSV import/export, attachments, offline sync | ⛔ Not started | Database tables exist (for import/attachments) | Everything else |
| Mobile app | 🟡 Written, unverified | Login screen, home screen, secure storage, networking, routing — all written | Has never been compiled or run; no platform folders (`ios/`, `android/`, etc.) exist yet; needs Flutter and, for macOS/iOS, full Xcode installed |
| Local development environment | ✅ Working | Docker Compose runs a real PostgreSQL; the backend runs and connects to it successfully | Nothing |
| Automated testing (backend) | ✅ Working | 81 tests, all passing, against a real database | Coverage of anything beyond auth, money, and dates |
| Automated testing (mobile) | 🟡 Written, unverified | One test file for the `Money` class | Has never actually been run, since Flutter isn't set up locally; will run for the first time on GitHub's servers |
| CI/CD (GitHub Actions) | ✅ Partially working | Backend and mobile checks run automatically on every push | Deployment step is intentionally inactive until Railway is set up |
| Production deployment | ⛔ Not started | Configuration file written | No live server exists anywhere |

---

## 12. What We Have Done So Far

### What we started with

A detailed written plan (`docs/PROJECT_PLAN.md`) describing the entire intended system, plus an
empty folder structure with hundreds of placeholder files matching that plan's layout — but no
actual working code.

### What we built, in order

1. **The complete database design.** Nine migration files were written, each adding a specific
   piece: tenancy and users, the "page engine" tables, attachments/imports, the dashboard, the
   tamper-evident audit log, security rules, the AI tables, the six real business tables, and
   finally the rate-limiting table. Every migration was actually run against a real PostgreSQL 18
   database (not just checked for correct syntax) — applied, reversed, and reapplied, to prove it
   genuinely works both ways.

2. **The application foundation.** Settings/configuration handling, database connection setup
   (including the deliberately separate, restricted connection meant for a future AI feature),
   standardized error responses, structured logging with automatic secret-scrubbing, and the
   `/health` endpoints that let a deployment system know the server is actually working.

3. **The complete login system.** Money handling, business-date handling, password hashing,
   JSON Web Tokens, refresh token rotation with theft detection, rate limiting, and the actual
   `/auth/login`, `/auth/refresh`, `/auth/logout`, and `/me` endpoints — all backed by 81 automated
   tests that run against a real database every time.

4. **Version control.** The entire project was placed under Git and pushed to GitHub for the
   first time, along with a real `README.md` and three GitHub Actions workflows to automatically
   check every future change.

5. **The beginning of the mobile app.** The Dart/Flutter equivalent of the money handling, secure
   token storage, the networking layer (with automatic token refresh and retry logic), and the
   login/home screens — written but not yet compiled or run, since the Flutter SDK isn't fully set
   up on the development machine yet.

### Important decisions we made, and why

- **Test against a real database, never a fake one.** This single decision caught two genuinely
  serious bugs that a fake/mocked database would have completely hidden: a transaction-rollback
  bug that would have silently disabled login lockout and, far more seriously, silently un-done
  the "revoke a stolen token" security response; and a permission conflict in the audit-log
  tamper-detection trigger.
- **The database itself enforces security, not just the application code.** Row-Level Security
  and the audit log's write-permission restrictions mean that even a future bug in the Python code
  can't automatically leak data between companies or rewrite history — PostgreSQL itself refuses.
- **Money is never a floating-point number, on either the server or the client.** A whole category
  of "the numbers don't add up" bugs is prevented by construction, not by being careful every
  single time.
- **The client (mobile app) never decides anything important.** It can hide a button, but it can
  never be the thing that actually enforces a rule — every real decision happens on the server,
  which is the only thing that can be trusted.

### Problems we encountered, and how they were solved

| Problem | How it was found | How it was fixed |
|---|---|---|
| The `app_user` database role had zero permissions on any table, making `REVOKE` statements meaningless no-ops | Manually testing the real database as that specific role, not as an all-powerful superuser | Added explicit `GRANT` statements once every table existed |
| The audit-log trigger needed a permission (`UPDATE`) that the same table explicitly forbids the application from having | Same manual real-database testing | Made the trigger function run with its own elevated, trusted permissions, separate from the application's normal restricted permissions |
| A database transaction wrapper silently undid important security actions (lockout counters, theft-response token revocation) whenever the underlying function raised an error | An automated test that checked the database state *after* a detected token-theft attempt | Rewrote the service functions to commit their own changes before raising any error |
| PostgreSQL 18's Docker image expects a different folder layout for its data than older versions | The database container failed to start with a clear error message | Corrected the Docker Compose file's volume configuration |
| Two real Dart bugs (an invalid `factory` constructor on an enum type, and a `const` keyword used on a constructor that isn't actually `const`) | Careful manual line-by-line review, since no Flutter compiler was available | Both fixed directly in the source |
| An initial Flutter SDK download was silently corrupted/incomplete | Checking the downloaded file's checksum against the official expected value | The corrupted file was deleted and the download was retried |

### Current state of the project (as of this document)

Three commits exist in Git history, all pushed to GitHub. The backend has a working, tested login
system sitting on top of a complete, tested database design. The mobile app has matching
(but unverified) client-side code for that same login system. Nothing beyond login/session
management has been built yet for any actual business feature.

---

## 13. If I Know Nothing About This Project, What Should I Understand First?

### The simplest possible explanation

This is an app for one supermarket to replace their paper books and spreadsheets with something
safer and, eventually, smarter. Right now, the **only thing that actually works** is: someone can
log in, stay logged in, and log out — securely. Nothing about actually recording money yet exists
in working code, even though the database is fully designed and ready for it.

### Recommended learning order

1. **Start with this file** (`PROJECT_DOCUMENTATION.md`) — you've just read it, so you already
   have the big picture.

2. **Read `README.md`** at the project root — it's short, and it'll show you exactly how to get
   the backend running on your own machine (Docker, then `uv sync`, then `alembic upgrade head`,
   then `uvicorn`). Actually running it will make everything else click faster than reading alone.

3. **Read `apps/api/app/core/money.py` and `apps/api/app/core/dates.py`.** These are short,
   simple, and self-contained — a gentle way to see the coding style and level of care used
   throughout the project, without needing to understand the database or networking yet.

4. **Read `apps/api/app/models/user.py` and `apps/api/app/db/base.py`.** This shows you what a
   database table looks like as Python code, and the shared building blocks every other table
   will eventually reuse.

5. **Read the migrations, in order, starting with
   `apps/api/alembic/versions/0001_tenancy_and_users.py`.** These are written with real SQL
   inside comments and explanations — reading them in order tells the story of how the database
   grew, piece by piece.

6. **Read `apps/api/app/services/auth_service.py`**, then `apps/api/app/routers/auth.py`. This is
   the heart of everything that currently works. Pay special attention to the comment at the top
   of `auth_service.py` explaining *why* every function commits its own changes before raising an
   error — that one detail is the most subtle and important lesson in the whole codebase so far.

7. **Read `Section 8 (Database)` and `Section 9 (Authentication and Security)` of this document
   again**, now that you've seen the real code — they should make much more sense the second time.

8. **Only after all that, look at the mobile app** (`apps/mobile/lib/features/auth/`) — it mirrors
   everything you just learned on the backend, just written in Dart instead of Python, for a phone
   screen instead of a server.

9. **Finally, skim `docs/PROJECT_PLAN.md`** to see the full destination this project is heading
   toward — but remember, as this document has repeated many times, most of that plan is not
   built yet. Use it to understand *where things are going*, not *what exists today*.

Once those nine steps are done, you'll understand not just what the code does, but *why* it was
written the way it was — which is the harder and more useful thing to actually carry forward.
