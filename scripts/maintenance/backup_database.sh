#!/bin/bash
# Database backup script for olms_multiyear
# Run nightly via Task Scheduler or cron
#
# Setup (Windows Task Scheduler):
#   Action: "C:\Program Files\Git\bin\bash.exe"
#   Arguments: -c "C:/Users/jakew/.local/bin/Labor Data Project_real/scripts/maintenance/backup_database.sh"
#   Trigger: Daily at 2:00 AM
#
# Setup (cron/WSL):
#   0 2 * * * /path/to/backup_database.sh

set -euo pipefail

# Configuration
DB_NAME="olms_multiyear"
DB_USER="postgres"
BACKUP_DIR="/c/Users/jakew/backups/olms"
RETAIN_DAYS=7

# Create backup directory if needed
mkdir -p "$BACKUP_DIR"

# Timestamp for filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/olms_${TIMESTAMP}.dump.gz"

echo "Starting backup of ${DB_NAME} at $(date)"

# Run pg_dump with custom format (most flexible for restore)
# Using gzip compression
pg_dump -U "$DB_USER" -Fc "$DB_NAME" | gzip > "$BACKUP_FILE"

# Verify backup was created and has reasonable size (> 1 GB for a 9.5 GB DB)
FILESIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo 0)
if [ "$FILESIZE" -lt 1000000000 ]; then
    echo "WARNING: Backup file is only ${FILESIZE} bytes (expected >1 GB)"
fi

echo "Backup complete: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Remove backups older than RETAIN_DAYS
echo "Cleaning backups older than ${RETAIN_DAYS} days..."
find "$BACKUP_DIR" -name "olms_*.dump.gz" -mtime +${RETAIN_DAYS} -delete 2>/dev/null || true

echo "Remaining backups:"
ls -lh "$BACKUP_DIR"/olms_*.dump.gz 2>/dev/null || echo "  (none)"

echo "Done at $(date)"
