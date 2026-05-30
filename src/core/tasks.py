"""
Core infrastructure tasks (backup, maintenance).
"""
import logging
import os
import subprocess
from datetime import datetime

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="core.tasks.backup_database")
def backup_database():
    """
    Run pg_dump and store backup with 7-day retention.
    Uses DATABASE_URL or individual PG* env vars.
    """
    backup_dir = os.environ.get("BACKUP_DIR", "/backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.sql.gz"
    filepath = os.path.join(backup_dir, filename)

    db_host = os.environ.get("POSTGRES_HOST", "postgres")
    db_port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "docai")
    db_user = os.environ.get("POSTGRES_USER", "docai")

    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ.get("POSTGRES_PASSWORD", "")

    cmd = (
        f"pg_dump -h {db_host} -p {db_port} -U {db_user} -d {db_name} "
        f"--no-owner --no-acl | gzip > {filepath}"
    )

    try:
        result = subprocess.run(
            cmd, shell=True, env=env,
            capture_output=True, text=True, timeout=600,
        )

        if result.returncode != 0:
            logger.error("Backup failed: %s", result.stderr)
            return {"status": "error", "error": result.stderr}

        size = os.path.getsize(filepath)
        logger.info("Backup created: %s (%d bytes)", filename, size)

        # Retention: remove backups older than 7 days
        _cleanup_old_backups(backup_dir, retention_days=7)

        return {"status": "ok", "file": filename, "size": size}

    except subprocess.TimeoutExpired:
        logger.error("Backup timed out after 600s")
        return {"status": "error", "error": "timeout"}
    except Exception as e:
        logger.error("Backup exception: %s", str(e))
        return {"status": "error", "error": str(e)}


def _cleanup_old_backups(backup_dir: str, retention_days: int = 7):
    """Remove backup files older than retention_days."""
    import time

    cutoff = time.time() - (retention_days * 86400)

    for f in os.listdir(backup_dir):
        if not f.startswith("backup_") or not f.endswith(".sql.gz"):
            continue
        fpath = os.path.join(backup_dir, f)
        if os.path.getmtime(fpath) < cutoff:
            os.remove(fpath)
            logger.info("Removed old backup: %s", f)
