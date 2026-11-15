#!/usr/bin/env bash
# ==============================================================================
# HabitPulse 1-Click Backup Script (Linux / macOS / Git Bash)
# Dumps the PostgreSQL database and archives user-uploaded media files.
# ==============================================================================
set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"

DB_USER="${DB_USER:-habit_user}"
DB_NAME="${DB_NAME:-habit_tracker}"

DB_BACKUP_FILE="${BACKUP_DIR}/habitpulse_db_${TIMESTAMP}.sql.gz"
MEDIA_BACKUP_FILE="${BACKUP_DIR}/habitpulse_media_${TIMESTAMP}.tar.gz"

echo "==> [1/2] Backing up PostgreSQL database from container habitpulse_db..."
docker exec -t habitpulse_db pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl | gzip > "$DB_BACKUP_FILE"
echo "    Database backup saved: $DB_BACKUP_FILE"

echo "==> [2/2] Backing up media files..."
if [ -d "./media" ]; then
  tar -czf "$MEDIA_BACKUP_FILE" -C . media
  echo "    Media backup saved: $MEDIA_BACKUP_FILE"
else
  echo "    No media folder found, skipping media archive."
fi

echo "==> [SUCCESS] Full snapshot complete! Both files are in ${BACKUP_DIR}/"
