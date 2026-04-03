#!/usr/bin/env bash
# backup-db.sh — Daily SQLite backup for ASI Track Manager
# Run via cron (see DEPLOYMENT.md Section 6)

set -e

APP_DIR="$HOME/apps/asi-track-manager"
BACKUP_DIR="$HOME/backups/asi-track-manager"
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/db_$TIMESTAMP.sqlite3"

mkdir -p "$BACKUP_DIR"

# Hot backup using sqlite3's .backup command (safe during active writes)
docker compose -f "$APP_DIR/docker-compose.yml" exec -T web \
    sqlite3 /app/db/db.sqlite3 ".backup /app/db/backup.sqlite3"

# Copy the backup file out of the container
CONTAINER=$(docker compose -f "$APP_DIR/docker-compose.yml" ps -q web)
docker cp "${CONTAINER}:/app/db/backup.sqlite3" "$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ]; then
    echo "Backup saved: $BACKUP_FILE"
else
    echo "ERROR: Backup FAILED — file not found at $BACKUP_FILE" >&2
    exit 1
fi

# Keep only the last 30 backups (30 days of daily backups)
ls -t "$BACKUP_DIR"/db_*.sqlite3 2>/dev/null | tail -n +31 | xargs -r rm --

echo "Cleanup complete. Kept last 30 backups."
