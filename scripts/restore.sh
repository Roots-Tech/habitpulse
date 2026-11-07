#!/usr/bin/env bash
# ==============================================================================
# HabitPulse 1-Click Disaster Recovery / Restore Script (Linux / macOS / Git Bash)
# Restores the PostgreSQL database and extracts user-uploaded media files.
# ==============================================================================
set -e

if [ -z "$1" ]; then
  echo "Usage: ./scripts/restore.sh <TIMESTAMP_OR_FILENAME>"
  echo "Example: ./scripts/restore.sh 20261107_133000"
  echo "     or: ./scripts/restore.sh ./backups/habitpulse_db_20261107_133000.sql.gz"
  exit 1
fi

INPUT="$1"
DB_USER="${DB_USER:-habit_user}"
DB_NAME="${DB_NAME:-habit_tracker}"

# Check if full path or timestamp was provided
if [ -f "$INPUT" ]; then
  DB_FILE="$INPUT"
  TIMESTAMP=$(basename "$INPUT" | sed 's/habitpulse_db_//' | sed 's/\.sql\.gz//')
  MEDIA_FILE="./backups/habitpulse_media_${TIMESTAMP}.tar.gz"
else
  TIMESTAMP="$INPUT"
  DB_FILE="./backups/habitpulse_db_${TIMESTAMP}.sql.gz"
  MEDIA_FILE="./backups/habitpulse_media_${TIMESTAMP}.tar.gz"
fi

if [ ! -f "$DB_FILE" ]; then
  echo "Error: Database backup file $DB_FILE not found!"
  exit 1
fi

echo "==> [1/2] Restoring PostgreSQL database into habitpulse_db from $DB_FILE..."
gunzip -c "$DB_FILE" | docker exec -i habitpulse_db psql -U "$DB_USER" -d "$DB_NAME"
echo "    Database restoration completed."

if [ -f "$MEDIA_FILE" ]; then
  echo "==> [2/2] Restoring Media files from $MEDIA_FILE..."
  tar -xzf "$MEDIA_FILE" -C .
  echo "    Media restoration completed."
else
  echo "    Notice: No matching media file found at $MEDIA_FILE, skipping media restoration."
fi

echo "==> [SUCCESS] Full system restoration complete! Application state restored."
