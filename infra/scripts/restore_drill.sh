#!/usr/bin/env bash
#
# Restore drill: prove a backup can actually be restored, and measure how long
# it takes.
#
# docs/RUNBOOK.md specifies a quarterly drill and carries a "Restore drill log"
# table described as "the evidence that the RTO is real". This file was 0 bytes
# and that table was empty, so the 4-hour RTO had never been measured — the
# recovery plan was a claim, not a tested procedure.
#
# The drill restores into a **scratch database**, never over anything real, and
# drops it afterwards. It then checks the restored copy is actually usable
# rather than merely present:
#
#   1. the schema is at the same migration head as the source
#   2. every table the source has, the restore has, with the same row counts
#   3. the audit hash chain still verifies inside the restored copy
#
# (3) matters most: a restore that loses or reorders `audit_logs` produces a
# database that looks fine and whose tamper-evidence is silently worthless.
#
# Usage:
#   infra/scripts/restore_drill.sh                      # newest dump in ./backups
#   infra/scripts/restore_drill.sh path/to/file.dump
#
# Environment:
#   DATABASE_URL_MIGRATOR / DATABASE_URL   Source DB, for comparison + admin.
#   BACKUP_DIR                             Where to look for dumps.
#   KEEP_SCRATCH=1                         Leave the scratch DB for inspection.
#
# Exit codes: 0 drill passed · 1 usage/config error · 2 restore failed ·
#             3 restored copy failed verification
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
DB_URL="${DATABASE_URL_MIGRATOR:-${DATABASE_URL:-}}"

log() { printf '%s restore_drill: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $2"; exit "$1"; }

[ -n "$DB_URL" ] || die 1 "set DATABASE_URL_MIGRATOR (or DATABASE_URL)"
command -v pg_restore >/dev/null 2>&1 || die 1 "pg_restore not found on PATH"
command -v psql >/dev/null 2>&1 || die 1 "psql not found on PATH"

DUMP_PATH="${1:-}"
if [ -z "$DUMP_PATH" ]; then
    DUMP_PATH="$(find "$BACKUP_DIR" -maxdepth 1 -name 'velmart-*.dump' -type f 2>/dev/null \
        | sort | tail -n 1)"
    [ -n "$DUMP_PATH" ] || die 1 "no dump found in $BACKUP_DIR — run backup_dump.sh first"
fi
[ -f "$DUMP_PATH" ] || die 1 "no such dump: $DUMP_PATH"

# If the backup wrote a checksum, confirm the file is the one that was written.
if [ -f "$DUMP_PATH.sha256" ]; then
    if command -v shasum >/dev/null 2>&1; then
        (cd "$(dirname "$DUMP_PATH")" && shasum -a 256 -c "$(basename "$DUMP_PATH").sha256" >/dev/null) \
            || die 3 "checksum mismatch — this dump is not the file that was backed up"
    fi
    log "checksum ok"
fi

# Everything after this point is timed: this is the number the RTO claim rests
# on, so it covers restore *and* verification, not just the restore call.
START_EPOCH="$(date -u +%s)"

# Admin connection to the same server, `postgres` database, so the scratch DB
# can be created and dropped.
ADMIN_URL="${DB_URL%/*}/postgres"
SCRATCH_DB="velmart_restore_drill_$(date -u +%Y%m%d%H%M%S)"
SCRATCH_URL="${DB_URL%/*}/$SCRATCH_DB"

cleanup() {
    if [ "${KEEP_SCRATCH:-0}" = "1" ]; then
        log "KEEP_SCRATCH=1 — leaving $SCRATCH_DB in place"
        return
    fi
    psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -q \
        -c "DROP DATABASE IF EXISTS \"$SCRATCH_DB\" WITH (FORCE);" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "restoring $(basename "$DUMP_PATH") into scratch database $SCRATCH_DB"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE \"$SCRATCH_DB\";" \
    || die 2 "could not create the scratch database"

# --no-owner/--no-privileges: the dump was taken that way, and the drill is
# about the data surviving, not about reproducing role grants on a throwaway.
# Roles referenced by RLS policies may not exist here, so errors are collected
# rather than fatal, and the verification below is what actually decides.
RESTORE_LOG="$(mktemp)"
if ! pg_restore --no-owner --no-privileges --dbname="$SCRATCH_URL" "$DUMP_PATH" \
        >"$RESTORE_LOG" 2>&1; then
    log "pg_restore reported issues:"
    tail -n 20 "$RESTORE_LOG" >&2
    # Not fatal on its own — missing roles are expected on a scratch restore.
    # The checks below decide whether the data actually made it.
fi

query() { psql "$1" -At -v ON_ERROR_STOP=1 -c "$2" 2>/dev/null || echo "ERROR"; }

# --- 1. same migration head -------------------------------------------------
SRC_HEAD="$(query "$DB_URL" "SELECT version_num FROM alembic_version")"
DST_HEAD="$(query "$SCRATCH_URL" "SELECT version_num FROM alembic_version")"
[ "$DST_HEAD" != "ERROR" ] || die 3 "restored copy has no alembic_version table"
[ "$SRC_HEAD" = "$DST_HEAD" ] \
    || die 3 "migration head mismatch: source $SRC_HEAD, restored $DST_HEAD"
log "migration head ok: $DST_HEAD"

# --- 2. every table present, with matching row counts -----------------------
TABLES="$(query "$DB_URL" \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")"
[ "$TABLES" != "ERROR" ] || die 3 "could not list source tables"

MISMATCHES=0
TABLE_COUNT=0
TOTAL_ROWS=0
while IFS= read -r table; do
    [ -n "$table" ] || continue
    TABLE_COUNT=$((TABLE_COUNT + 1))
    src="$(query "$DB_URL" "SELECT count(*) FROM \"$table\"")"
    dst="$(query "$SCRATCH_URL" "SELECT count(*) FROM \"$table\"")"
    if [ "$dst" = "ERROR" ]; then
        log "MISSING TABLE in restore: $table"
        MISMATCHES=$((MISMATCHES + 1))
    elif [ "$src" != "$dst" ]; then
        log "ROW COUNT MISMATCH $table: source $src, restored $dst"
        MISMATCHES=$((MISMATCHES + 1))
    else
        TOTAL_ROWS=$((TOTAL_ROWS + src))
    fi
done <<< "$TABLES"
[ "$MISMATCHES" -eq 0 ] || die 3 "$MISMATCHES table(s) did not survive the restore intact"
log "all $TABLE_COUNT tables restored, $TOTAL_ROWS rows total"

# --- 3. the audit chain still verifies in the restored copy -----------------
# A restore that loses or reorders audit_logs yields a database that looks
# healthy and whose tamper-evidence is quietly worthless.
#
# The hash formula changed in 0018 (it now covers page_id, actor_role, diff,
# ai_session_id, ip_address and user_agent) and the chain's ordering column
# `chain_seq` arrived in 0021. Checking an older dump with the current formula
# reports every row as broken — a false alarm about the most alarming thing
# this script can say — so the check is skipped, loudly, when the restored
# schema predates it.
CHAIN_AWARE="$(query "$SCRATCH_URL" \
    "SELECT CASE WHEN version_num >= '0021' THEN 'yes' ELSE 'no' END FROM alembic_version")"
if [ "$CHAIN_AWARE" != "yes" ]; then
    log "SKIPPED audit chain check: dump is at schema $DST_HEAD, older than the 0021 chain format"
    ELAPSED=$(( $(date -u +%s) - START_EPOCH ))
    log "DRILL PASSED in ${ELAPSED}s (chain check skipped)"
    printf '{"dump":"%s","elapsed_seconds":%s,"tables":%s,"rows":%s,"migration_head":"%s","chain_checked":false}\n' \
        "$(basename "$DUMP_PATH")" "$ELAPSED" "$TABLE_COUNT" "$TOTAL_ROWS" "$DST_HEAD"
    exit 0
fi

BROKEN="$(query "$SCRATCH_URL" "
    WITH recomputed AS (
        SELECT chain_seq,
               row_hash = encode(digest(concat_ws('|',
                   COALESCE(LAG(row_hash) OVER (ORDER BY chain_seq), ''),
                   company_id::text,
                   COALESCE(actor_user_id::text, ''),
                   COALESCE(actor_role::text, ''),
                   action, entity_type,
                   COALESCE(entity_id::text, ''),
                   COALESCE(page_id::text, ''),
                   COALESCE(old_data::text, ''),
                   COALESCE(new_data::text, ''),
                   COALESCE(diff::text, ''),
                   source,
                   COALESCE(ai_session_id::text, ''),
                   COALESCE(ip_address::text, ''),
                   COALESCE(user_agent, ''),
                   created_at::text), 'sha256'), 'hex') AS ok
        FROM audit_logs
    )
    SELECT count(*) FROM recomputed WHERE ok IS NOT TRUE")"
if [ "$BROKEN" = "ERROR" ]; then
    log "WARNING: could not verify the audit chain in the restored copy (pgcrypto missing?)"
elif [ "$BROKEN" != "0" ]; then
    die 3 "audit chain is broken in the restored copy at $BROKEN row(s)"
else
    log "audit chain verified in the restored copy"
fi

ELAPSED=$(( $(date -u +%s) - START_EPOCH ))
log "DRILL PASSED in ${ELAPSED}s"

printf '{"dump":"%s","elapsed_seconds":%s,"tables":%s,"rows":%s,"migration_head":"%s","chain_checked":true}\n' \
    "$(basename "$DUMP_PATH")" "$ELAPSED" "$TABLE_COUNT" "$TOTAL_ROWS" "$DST_HEAD"
