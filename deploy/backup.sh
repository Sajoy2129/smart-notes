#!/usr/bin/env bash
# Nightly backup of the Smart Notes database. cron runs it on the server
# (see deploy/README.md). The two arguments are only for tests.
#
# Usage: backup.sh [database file] [backup folder]

# Stop at the first error, and treat unset variables as errors.
set -euo pipefail

DB="${1:-/home/ubuntu/data/smart_notes.db}"
BACKUP_DIR="${2:-/home/ubuntu/data/backups}"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

# .backup makes a safe copy even if the app is writing at the same moment,
# unlike cp. One file per day, e.g. smart_notes-2026-10-27.db.
sqlite3 "$DB" ".backup '$BACKUP_DIR/smart_notes-$(date +%F).db'"

# Delete backups older than KEEP_DAYS days, so the disk never fills up.
find "$BACKUP_DIR" -name 'smart_notes-*.db' -mtime +"$KEEP_DAYS" -delete
