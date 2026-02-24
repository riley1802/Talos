#!/bin/bash
# genesis.sh — Talos v4.0 host directory setup
# Run once before `docker compose up`
# Usage: bash scripts/genesis.sh

set -euo pipefail

TALOS_ROOT="${HOME}/talos"
TALOS_UID="${TALOS_UID:-1000}"
TALOS_GID="${TALOS_GID:-1000}"

log() { echo "[GENESIS] $*"; }

log "Creating Talos directory hierarchy at ${TALOS_ROOT}..."

# Root
mkdir -p "${TALOS_ROOT}"
chmod 755 "${TALOS_ROOT}"

# Skills
mkdir -p "${TALOS_ROOT}/skills/quarantine"
mkdir -p "${TALOS_ROOT}/skills/active"
mkdir -p "${TALOS_ROOT}/skills/deprecated"
chmod 755 "${TALOS_ROOT}/skills"
chmod 750 "${TALOS_ROOT}/skills/quarantine"
chmod 755 "${TALOS_ROOT}/skills/active"
chmod 750 "${TALOS_ROOT}/skills/deprecated"

# Keys — maximum restriction
mkdir -p "${TALOS_ROOT}/keys"
chmod 700 "${TALOS_ROOT}/keys"

# Logs — tiered permissions
mkdir -p "${TALOS_ROOT}/logs/tier1"
mkdir -p "${TALOS_ROOT}/logs/tier2"
mkdir -p "${TALOS_ROOT}/logs/tier3"
chmod 755 "${TALOS_ROOT}/logs"
chmod 750 "${TALOS_ROOT}/logs/tier1"
chmod 750 "${TALOS_ROOT}/logs/tier2"
chmod 755 "${TALOS_ROOT}/logs/tier3"

# Data
mkdir -p "${TALOS_ROOT}/data/redis"
mkdir -p "${TALOS_ROOT}/data/chromadb"
chmod 755 "${TALOS_ROOT}/data"
chmod 700 "${TALOS_ROOT}/data/redis"
chmod 700 "${TALOS_ROOT}/data/chromadb"

# Config, backups, tmp
mkdir -p "${TALOS_ROOT}/config"
chmod 755 "${TALOS_ROOT}/config"

mkdir -p "${TALOS_ROOT}/backups"
chmod 750 "${TALOS_ROOT}/backups"

mkdir -p "${TALOS_ROOT}/tmp"
chmod 1777 "${TALOS_ROOT}/tmp"

# Set ownership
chown -R "${TALOS_UID}:${TALOS_GID}" "${TALOS_ROOT}"

log "Done. Directory tree:"
find "${TALOS_ROOT}" -maxdepth 3 -type d | sort | sed 's|'"${HOME}"'|~|g'

log ""
log "Next steps:"
log "  1. Copy talos.env to ~/talos/config/talos.env"
log "  2. Set GEMINI_API_KEY and BASIC_AUTH_PASS in ~/talos/config/talos.env"
log "  3. chmod 600 ~/talos/config/talos.env"
log "  4. docker compose up -d"
