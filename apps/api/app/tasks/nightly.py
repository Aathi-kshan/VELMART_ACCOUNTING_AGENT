"""`python -m app.tasks.nightly` — the nightly cron entrypoint
(docs/PROJECT_PLAN.md §23.2/§25): audit chain verify, `pg_dump` backup,
idempotency cleanup, daily digest, in that order.

Each job runs independently — one failing must not silently skip the rest,
so every job is wrapped in its own try/except and reported in one final
structured summary. Exits non-zero if any job failed or the audit chain
came back broken, so the cron runner (and whatever it forwards to Sentry
or a monitoring hook) actually notices.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.logging import configure_logging, get_logger
from app.db.migrator import dispose_migrator_engine
from app.db.session import dispose_engine
from app.tasks import audit_chain_verify, daily_digest, export_build, idempotency_cleanup

log = get_logger(__name__)


async def main() -> int:
    configure_logging()
    results: dict[str, object] = {}
    failed: list[str] = []

    try:
        chain = await audit_chain_verify.run()
        results["chain_verify"] = {
            "rows_checked": chain.rows_checked,
            "is_valid": chain.is_valid,
            "first_broken_id": chain.first_broken_id,
        }
        if not chain.is_valid:
            failed.append("chain_verify")
    except Exception:
        log.exception("nightly.chain_verify_failed")
        failed.append("chain_verify")

    try:
        backup = await export_build.run()
        results["backup"] = {"dump_path": str(backup.dump_path), "size_bytes": backup.size_bytes}
    except Exception:
        log.exception("nightly.backup_failed")
        failed.append("backup")

    try:
        deleted = await idempotency_cleanup.run()
        results["idempotency_cleanup"] = {"deleted": deleted}
    except Exception:
        log.exception("nightly.idempotency_cleanup_failed")
        failed.append("idempotency_cleanup")

    try:
        digest = await daily_digest.run()
        results["digest"] = {
            "companies_processed": digest.companies_processed,
            "digest_date": digest.digest_date.isoformat(),
        }
    except Exception:
        log.exception("nightly.digest_failed")
        failed.append("digest")

    await dispose_migrator_engine()
    await dispose_engine()

    log.info("nightly.summary", results=results, failed=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
