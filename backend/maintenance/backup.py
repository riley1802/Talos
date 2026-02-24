"""Backup and restore logic.

Wraps the bash scripts for creating and restoring backups.
"""
import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"

async def create_backup() -> bool:
    """Run the backup.sh script to create a tar.gz archive of state."""
    script_path = SCRIPTS_DIR / "backup.sh"
    if not script_path.exists():
        logger.error("Backup script not found at %s", script_path)
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Backup created successfully\n%s", stdout.decode())
            return True
        else:
            logger.error("Backup failed with code %d:\n%s", proc.returncode, stderr.decode())
            return False
    except Exception as exc:
        logger.error("Backup exception: %s", exc)
        return False

async def restore_backup(archive_path: str) -> bool:
    """Run the restore.sh script to restore from an archive."""
    script_path = SCRIPTS_DIR / "restore.sh"
    if not script_path.exists():
        logger.error("Restore script not found at %s", script_path)
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script_path), archive_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Restore successful\n%s", stdout.decode())
            return True
        else:
            logger.error("Restore failed with code %d:\n%s", proc.returncode, stderr.decode())
            return False
    except Exception as exc:
        logger.error("Restore exception: %s", exc)
        return False
