#!/bin/bash
# restore.sh — Restore Talos from a backup archive
# Usage: bash scripts/restore.sh ~/talos/backups/backup_YYYYMMDD_HHMMSS.tar.gz

set -euo pipefail

BACKUP_FILE="${1:-}"
TALOS_ROOT="${HOME}/talos"

log()  { echo "[RESTORE] $*"; }
die()  { echo "[RESTORE:ERROR] $*" >&2; exit 1; }

[[ -z "${BACKUP_FILE}" ]] && die "Usage: $0 <backup_file.tar.gz>"
[[ -f "${BACKUP_FILE}" ]] || die "Backup file not found: ${BACKUP_FILE}"

log "Restoring from: ${BACKUP_FILE}"

# Verify checksum if available
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "${CHECKSUM_FILE}" ]]; then
    log "Verifying checksum..."
    sha256sum --check "${CHECKSUM_FILE}" || die "Checksum verification FAILED"
    log "Checksum OK"
else
    log "WARNING: No checksum file found — skipping verification"
fi

# Stop running containers before restore
log "Stopping Talos containers..."
docker compose -f "$(dirname "$0")/../docker-compose.yml" down 2>/dev/null || true

# Backup current state before overwriting
SAFEGUARD="${TALOS_ROOT}/backups/pre-restore_$(date +%Y%m%d_%H%M%S).tar.gz"
log "Safeguarding current state → ${SAFEGUARD}"
tar -czf "${SAFEGUARD}" \
    -C "${HOME}" \
    talos/data/redis talos/data/chromadb talos/skills/active talos/config 2>/dev/null || true

# Extract backup
log "Extracting backup..."
tar -xzf "${BACKUP_FILE}" -C "${HOME}"

log "Restore complete"
log ""
log "Next step: docker compose up -d"
