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

Until then the destination matters. This wrote into `tempfile.gettempdir()`,
which on a container platform is ephemeral: every dump was discarded on the
next redeploy, so even once the job was scheduled it would have produced no
retained backup at all. `BACKUP_DIR` now points it at a mounted volume, and
the task says plainly in its result whether the directory it used is
persistent, rather than reporting success for a file about to vanish.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core.logging import get_logger
from app.db.migrator import MigratorEngineUnavailableError

log = get_logger(__name__)


class BackupFailedError(RuntimeError):
    """`pg_dump` did not produce a dump, with the reason it gave."""


@dataclass(frozen=True)
class BackupResult:
    dump_path: Path
    size_bytes: int
    #: Always `False` in this pass — see the module docstring.
    uploaded: bool
    #: False when the dump landed in a temp directory, which on a container
    #: platform is discarded on the next redeploy. Surfaced so "the backup
    #: succeeded" cannot be read as "a backup exists" when it does not.
    persistent: bool


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
    configured = settings.BACKUP_DIR
    persistent = bool(configured)
    backup_dir = Path(configured) if configured else Path(tempfile.gettempdir())
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_path = backup_dir / f"velmart-{today}.dump"

    def _run_pg_dump() -> None:
        # S603/S607 justifications: fixed argv, no shell, no user input in
        # the command line; `pg_dump` resolved via PATH (installed as
        # `postgresql-client-18` by infra/Dockerfile.api) rather than a
        # hardcoded absolute path, which would be brittle across environments.
        argv = [  # noqa: S607
            "pg_dump",
            "--format=custom",
            f"--file={dump_path}",
            migrator_url,
        ]
        result = subprocess.run(argv, check=False, capture_output=True, text=True)  # noqa: S603
        if result.returncode != 0:
            # `check=True` alone raises a CalledProcessError whose message is
            # just the argv and the exit status — `capture_output` having
            # swallowed the reason. That is how a plain version mismatch
            # ("server version 18.6; pg_dump version 17.11") reached the
            # nightly log as an unexplained non-zero exit, with the one line
            # that identified the problem discarded. A backup failure has to
            # say why it failed.
            detail = (result.stderr or result.stdout or "").strip()
            raise BackupFailedError(
                f"pg_dump exited {result.returncode}: {detail or 'no output'}"
            )

    # A nightly, one-shot script process — blocking the event loop briefly
    # here costs nothing, but `to_thread` keeps this importable/testable
    # from async code without that caveat needing to be rediscovered later.
    await asyncio.to_thread(_run_pg_dump)

    if not persistent:
        log.warning(
            "backup.not_persistent",
            dump_path=str(dump_path),
            detail="BACKUP_DIR is unset, so this dump is in a temp directory and will "
            "not survive a redeploy. Set BACKUP_DIR to a mounted volume.",
        )

    return BackupResult(
        dump_path=dump_path,
        size_bytes=dump_path.stat().st_size,
        uploaded=False,
        persistent=persistent,
    )
