"""Nightly `pg_dump` backup (docs/PROJECT_PLAN.md §25, P5) — **not** CSV
export (`app/services/csv_service.py`/`app/routers/exports.py` already do
that; this is the off-platform database backup the ops runbook calls for
alongside Railway's own managed daily backups).

Dumps the whole database — schema and rows together, so `pages`/
`page_columns` are backed up exactly as durably as the records they
describe (§25: "a backup that restores records but loses `pages` and
`page_columns` restores meaningless JSONB").

**Uploading the dump to the bucket is deferred**, the same explicit scope
decision as the Attachments slice's S3 storage work — `app/storage/` stays
an empty stub for this pass. This task proves the dump itself succeeds and
reports where it landed locally; wiring it to a bucket upload is a small,
contained follow-up once that storage layer exists.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db.migrator import MigratorEngineUnavailableError


@dataclass(frozen=True)
class BackupResult:
    dump_path: Path
    size_bytes: int
    #: Always `False` in this pass — see the module docstring.
    uploaded: bool


async def run() -> BackupResult:
    """Runs `pg_dump` against the `migrator` connection (schema owner —
    `app_user`'s DML-only grants aren't guaranteed sufficient for a
    complete schema dump) and writes a custom-format dump to a local temp
    file, one per day."""
    settings = get_settings()
    migrator_url = settings.DATABASE_URL_MIGRATOR
    if not migrator_url:
        raise MigratorEngineUnavailableError(
            "DATABASE_URL_MIGRATOR is not configured; the nightly backup requires the "
            "migrator role for a complete schema+data dump."
        )

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    dump_path = Path(tempfile.gettempdir()) / f"velmart-{today}.dump"

    def _run_pg_dump() -> None:
        # S603/S607 justifications: fixed argv, no shell, no user input in
        # the command line; `pg_dump` resolved via PATH (as the Docker image
        # provides it) rather than a hardcoded absolute path, which would be
        # brittle across environments.
        argv = [  # noqa: S607
            "pg_dump",
            "--format=custom",
            f"--file={dump_path}",
            migrator_url,
        ]
        subprocess.run(argv, check=True, capture_output=True)  # noqa: S603

    # A nightly, one-shot script process — blocking the event loop briefly
    # here costs nothing, but `to_thread` keeps this importable/testable
    # from async code without that caveat needing to be rediscovered later.
    await asyncio.to_thread(_run_pg_dump)

    return BackupResult(dump_path=dump_path, size_bytes=dump_path.stat().st_size, uploaded=False)
