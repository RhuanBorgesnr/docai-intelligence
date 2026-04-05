#!/bin/bash
# Backup script for PostgreSQL database
# Usage: ./backup.sh

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql.gz"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Create backup
echo "Creating backup: $BACKUP_FILE"
PGPASSWORD=$DB_PASSWORD pg_dump -h postgres -U $DB_USER $DB_NAME | gzip > $BACKUP_FILE

# Keep only last 7 days of backups
echo "Cleaning old backups..."
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
ls -la $BACKUP_DIR
