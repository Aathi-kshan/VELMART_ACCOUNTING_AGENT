#!/usr/bin/env bash
#
# Logical backup of the Velmart database.
#
# docs/RUNBOOK.md has described this file as the mechanism behind a "90-day
# retained logical backup" since before it was written — the file was 0 bytes,
# so no backup of any kind existed. This is that mechanism.
#
# It dumps schema and data together, deliberately: a backup that restores
# `records` but loses `pages`/`page_columns` restores meaningless JSONB,
# because a generic page's rows are only interpretable through the column
# definitions that describe them.
#
# The dump is verified before it is kept. An unreadable backup discovered
# during a restore is worse than a missing one, because it was counted on.
#
# Usage:
#   infra/scripts/backup_dump.sh
#   BACKUP_DIR=/mnt/backups RETENTION_DAYS=90 infra/scripts/backup_dump.sh
#
# Environment:
#   DATABASE_URL_MIGRATOR  Connection string. The migrator role owns the
#                          schema; app_user's DML-only grants are not
#                          guaranteed sufficient for a complete schema dump.
#   DATABASE_URL           Fallback if the above is unset.
#   BACKUP_DIR             Where dumps land (default: ./backups).
#   RETENTION_DAYS         Days to keep (default: 90, matching the RUNBOOK).
#
# Exit codes: 0 success · 1 usage/config error · 2 dump failed ·
#             3 dump failed verification
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-90}"
DB_URL="${DATABASE_URL_MIGRATOR:-${DATABASE_URL:-}}"

log() { printf '%s backup_dump: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $2"; exit "$1"; }

[ -n "$DB_URL" ] || die 1 "set DATABASE_URL_MIGRATOR (or DATABASE_URL) to the database to back up"
command -v pg_dump >/dev/null 2>&1 || die 1 "pg_dump not found on PATH"
command -v pg_restore >/dev/null 2>&1 || die 1 "pg_restore not found on PATH (needed to verify)"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_PATH="$BACKUP_DIR/velmart-$STAMP.dump"

log "dumping to $DUMP_PATH"
# --format=custom so pg_restore can do a selective/parallel restore, and so
# the dump is compressed without a separate step.
if ! pg_dump --format=custom --no-owner --no-privileges --file="$DUMP_PATH" "$DB_URL"; then
    rm -f "$DUMP_PATH"
    die 2 "pg_dump failed; no partial dump left behind"
fi

# Verify before trusting it. `pg_restore --list` parses the archive's table of
# contents, so a truncated or corrupt dump fails here rather than during a
# real recovery.
if ! pg_restore --list "$DUMP_PATH" >/dev/null 2>&1; then
    rm -f "$DUMP_PATH"
    die 3 "dump did not survive verification and was discarded"
fi

OBJECT_COUNT="$(pg_restore --list "$DUMP_PATH" | grep -c '^[0-9]' || true)"
SIZE_BYTES="$(wc -c <"$DUMP_PATH" | tr -d ' ')"
[ "$OBJECT_COUNT" -gt 0 ] || die 3 "dump verified as readable but contains no objects"

# A checksum beside the dump, so a later restore can prove the file it is
# reading is the file that was written.
if command -v shasum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && shasum -a 256 "$(basename "$DUMP_PATH")" > "$(basename "$DUMP_PATH").sha256")
elif command -v sha256sum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && sha256sum "$(basename "$DUMP_PATH")" > "$(basename "$DUMP_PATH").sha256")
fi

log "ok: $SIZE_BYTES bytes, $OBJECT_COUNT objects"

# Prune old dumps last, and only after a good one exists — never leave the
# window with no backup because pruning ran before a failed dump.
PRUNED=0
while IFS= read -r old; do
    rm -f "$old" "$old.sha256"
    PRUNED=$((PRUNED + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'velmart-*.dump' -type f -mtime "+$RETENTION_DAYS" 2>/dev/null)
[ "$PRUNED" -eq 0 ] || log "pruned $PRUNED dump(s) older than $RETENTION_DAYS days"

REMAINING="$(find "$BACKUP_DIR" -maxdepth 1 -name 'velmart-*.dump' -type f | wc -l | tr -d ' ')"
log "retained $REMAINING dump(s) in $BACKUP_DIR"

# Machine-readable last line, so a cron wrapper can record it without parsing
# the human log above.
printf '{"dump_path":"%s","size_bytes":%s,"objects":%s,"retained":%s}\n' \
    "$DUMP_PATH" "$SIZE_BYTES" "$OBJECT_COUNT" "$REMAINING"
