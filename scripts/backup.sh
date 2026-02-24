#!/bin/bash
# backup.sh — Create a timestamped backup of Talos data
# Usage: bash scripts/backup.sh
# Output: ~/talos/backups/backup_YYYYMMDD_HHMMSS.tar.gz

set -euo pipefail

TALOS_ROOT="${HOME}/talos"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${TALOS_ROOT}/backups/backup_${TIMESTAMP}.tar.gz"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

log() { echo "[BACKUP] $*"; }

log "Starting backup — ${TIMESTAMP}"
log "Target: ${BACKUP_FILE}"

# Ensure backups directory exists
mkdir -p "${TALOS_ROOT}/backups"

# Create backup archive
tar -czf "${BACKUP_FILE}" \
    -C "${HOME}" \
    --exclude="talos/data/redis/*.rdb.tmp" \
    --exclude="talos/tmp/*" \
    talos/data/redis \
    talos/data/chromadb \
    talos/skills/active \
    talos/config \
    talos/logs/tier1

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
log "Archive created: ${BACKUP_SIZE}"

# Generate checksum
sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
log "Checksum: $(cat "${CHECKSUM_FILE}")"

# Prune old backups (keep last 30 days)
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
find "${TALOS_ROOT}/backups" -name "backup_*.tar.gz" -mtime "+${RETENTION_DAYS}" -delete
find "${TALOS_ROOT}/backups" -name "backup_*.tar.gz.sha256" -mtime "+${RETENTION_DAYS}" -delete
log "Pruned backups older than ${RETENTION_DAYS} days"

log "Backup complete: ${BACKUP_FILE}"
