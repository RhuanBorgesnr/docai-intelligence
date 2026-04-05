#!/bin/bash
# Restore script for PostgreSQL database
# Usage: ./restore.sh backup_file.sql.gz

set -e

if [ -z "$1" ]; then
    echo "Usage: ./restore.sh backup_file.sql.gz"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "WARNING: This will overwrite the current database!"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo "Restoring from: $BACKUP_FILE"

# Drop and recreate database
PGPASSWORD=$DB_PASSWORD psql -h postgres -U $DB_USER -c "DROP DATABASE IF EXISTS $DB_NAME;"
PGPASSWORD=$DB_PASSWORD psql -h postgres -U $DB_USER -c "CREATE DATABASE $DB_NAME;"

# Restore
gunzip -c $BACKUP_FILE | PGPASSWORD=$DB_PASSWORD psql -h postgres -U $DB_USER $DB_NAME

echo "Restore completed successfully!"
