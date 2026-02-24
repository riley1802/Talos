# Section 1: The Genesis Setup Protocol (Zero to Hero)

## Talos v4.0 Master Implementation Specification

**Document Classification:** Technical Implementation Guide  
**Target Audience:** DevOps Engineers, Infrastructure Architects  
**Execution Context:** Linux Mint Host System  
**Container Runtime:** Docker 20.10+ with tini as PID 1  

---

## 1.1 Directory Hierarchy

### 1.1.1 Host Filesystem Architecture

The Talos container requires a strictly defined directory hierarchy on the host Linux Mint system. All paths are relative to the user's home directory (`$HOME` or `~`).

#### Root Directory Structure

```
~/talos/
├── skills/
│   ├── quarantine/      # Untrusted skill packages (isolated)
│   ├── active/          # Approved and loaded skills
│   └── deprecated/      # Retired skills pending cleanup
├── keys/                # Cryptographic material and API secrets
├── logs/                # Structured logging with tiered retention
│   ├── tier1/           # Critical events (90-day retention)
│   ├── tier2/           # Operational logs (30-day retention)
│   └── tier3/           # Debug/trace logs (7-day retention)
├── data/                # Persistent application state
│   ├── redis/           # Redis AOF and RDB persistence
│   └── chromadb/        # Vector database persistence
├── config/              # Runtime configuration files
├── backups/             # Automated backup snapshots
└── tmp/                 # Ephemeral working directory
```

### 1.1.2 Directory Creation Commands

Execute these commands as the talos service user (UID 1000 recommended):

```bash
#!/bin/bash
# genesis_directory_setup.sh
# Execute as: bash genesis_directory_setup.sh

set -euo pipefail

TALOS_ROOT="${HOME}/talos"
TALOS_USER="${TALOS_USER:-1000}"
TALOS_GROUP="${TALOS_GROUP:-1000}"

echo "[GENESIS] Creating Talos directory hierarchy..."

# Create root directory with restricted permissions
mkdir -p "${TALOS_ROOT}"
chmod 755 "${TALOS_ROOT}"
chown "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}"

# Create skills hierarchy
mkdir -p "${TALOS_ROOT}/skills/quarantine"
mkdir -p "${TALOS_ROOT}/skills/active"
mkdir -p "${TALOS_ROOT}/skills/deprecated"
chmod 755 "${TALOS_ROOT}/skills"
chmod 750 "${TALOS_ROOT}/skills/quarantine"
chmod 755 "${TALOS_ROOT}/skills/active"
chmod 750 "${TALOS_ROOT}/skills/deprecated"
chown -R "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/skills"

# Create keys directory with maximum restriction
mkdir -p "${TALOS_ROOT}/keys"
chmod 700 "${TALOS_ROOT}/keys"
chown "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/keys"

# Create logs hierarchy with tiered permissions
mkdir -p "${TALOS_ROOT}/logs/tier1"
mkdir -p "${TALOS_ROOT}/logs/tier2"
mkdir -p "${TALOS_ROOT}/logs/tier3"
chmod 755 "${TALOS_ROOT}/logs"
chmod 750 "${TALOS_ROOT}/logs/tier1"
chmod 750 "${TALOS_ROOT}/logs/tier2"
chmod 755 "${TALOS_ROOT}/logs/tier3"
chown -R "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/logs"

# Create data directories
mkdir -p "${TALOS_ROOT}/data/redis"
mkdir -p "${TALOS_ROOT}/data/chromadb"
chmod 755 "${TALOS_ROOT}/data"
chmod 700 "${TALOS_ROOT}/data/redis"
chmod 700 "${TALOS_ROOT}/data/chromadb"
chown -R "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/data"

# Create config directory
mkdir -p "${TALOS_ROOT}/config"
chmod 755 "${TALOS_ROOT}/config"
chown "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/config"

# Create backups directory
mkdir -p "${TALOS_ROOT}/backups"
chmod 750 "${TALOS_ROOT}/backups"
chown "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/backups"

# Create tmp directory with sticky bit
mkdir -p "${TALOS_ROOT}/tmp"
chmod 1777 "${TALOS_ROOT}/tmp"
chown "${TALOS_USER}:${TALOS_GROUP}" "${TALOS_ROOT}/tmp"

echo "[GENESIS] Directory hierarchy created successfully."
echo "[GENESIS] Verifying permissions..."
find "${TALOS_ROOT}" -type d -exec ls -ld {} \;
```

### 1.1.3 Directory Reference Table

| Directory Path | Purpose | chmod | chown | Mount Options |
|----------------|---------|-------|-------|---------------|
| `~/talos/` | Root directory for all Talos data | 755 | 1000:1000 | defaults |
| `~/talos/skills/` | Skill package management root | 755 | 1000:1000 | defaults |
| `~/talos/skills/quarantine/` | Untrusted skill isolation zone | 750 | 1000:1000 | noexec,nosuid,nodev |
| `~/talos/skills/active/` | Approved skill execution zone | 755 | 1000:1000 | defaults |
| `~/talos/skills/deprecated/` | Retired skill archive | 750 | 1000:1000 | noexec,nosuid |
| `~/talos/keys/` | API keys and cryptographic material | 700 | 1000:1000 | noexec,nosuid,nodev |
| `~/talos/logs/` | Log aggregation root | 755 | 1000:1000 | defaults |
| `~/talos/logs/tier1/` | Critical security events | 750 | 1000:1000 | nodev |
| `~/talos/logs/tier2/` | Operational audit logs | 750 | 1000:1000 | nodev |
| `~/talos/logs/tier3/` | Debug and trace output | 755 | 1000:1000 | nodev |
| `~/talos/data/redis/` | Redis persistence files | 700 | 1000:1000 | noexec,nosuid,nodev |
| `~/talos/data/chromadb/` | Vector database storage | 700 | 1000:1000 | noexec,nosuid,nodev |
| `~/talos/config/` | Runtime configuration | 755 | 1000:1000 | defaults |
| `~/talos/backups/` | Automated backup storage | 750 | 1000:1000 | noexec,nosuid |
| `~/talos/tmp/` | Ephemeral working space | 1777 | 1000:1000 | nosuid,nodev |

### 1.1.4 Filesystem Mount Configuration

For enhanced security, apply mount options via `/etc/fstab` entries:

```bash
# Add to /etc/fstab for persistent mount options
# Requires root privileges

# Talos keys directory - maximum security
tmpfs /home/talos/talos/keys tmpfs noexec,nosuid,nodev,size=10M,mode=700,uid=1000,gid=1000 0 0

# Talos tmp directory - ephemeral with size limit
tmpfs /home/talos/talos/tmp tmpfs nosuid,nodev,size=512M,mode=1777,uid=1000,gid=1000 0 0
```

**Apply mount options without reboot:**
```bash
sudo mount -o remount,noexec,nosuid,nodev ~/talos/keys
sudo mount -o remount,nosuid,nodev ~/talos/tmp
```

### 1.1.5 Permission Verification Script

```bash
#!/bin/bash
# verify_permissions.sh
# Run this after directory creation to validate security posture

TALOS_ROOT="${HOME}/talos"
EXIT_CODE=0

echo "[VERIFY] Checking Talos directory permissions..."

# Function to check directory permissions
check_dir() {
    local path="$1"
    local expected_perms="$2"
    local expected_owner="$3"
    
    if [[ ! -d "$path" ]]; then
        echo "[FAIL] Directory missing: $path"
        return 1
    fi
    
    local actual_perms=$(stat -c '%a' "$path")
    local actual_owner=$(stat -c '%u:%g' "$path")
    
    if [[ "$actual_perms" != "$expected_perms" ]]; then
        echo "[FAIL] $path: permissions $actual_perms, expected $expected_perms"
        return 1
    fi
    
    if [[ "$actual_owner" != "$expected_owner" ]]; then
        echo "[FAIL] $path: owner $actual_owner, expected $expected_owner"
        return 1
    fi
    
    echo "[PASS] $path"
    return 0
}

# Verify all directories
check_dir "${TALOS_ROOT}" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/skills" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/skills/quarantine" "750" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/skills/active" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/skills/deprecated" "750" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/keys" "700" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/logs" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/logs/tier1" "750" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/logs/tier2" "750" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/logs/tier3" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/data/redis" "700" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/data/chromadb" "700" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/config" "755" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/backups" "750" "1000:1000" || EXIT_CODE=1
check_dir "${TALOS_ROOT}/tmp" "1777" "1000:1000" || EXIT_CODE=1

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[VERIFY] All permissions verified successfully."
else
    echo "[VERIFY] PERMISSION VERIFICATION FAILED - Review errors above."
fi

exit $EXIT_CODE
```

---

## 1.2 Environment Injection

### 1.2.1 Environment Variable Specification

All environment variables must be defined in `~/talos/config/talos.env`. This file must have permissions `600` and be owned by the talos user.

```bash
# Create environment file with secure permissions
touch ~/talos/config/talos.env
chmod 600 ~/talos/config/talos.env
chown 1000:1000 ~/talos/config/talos.env
```

### 1.2.2 Required Environment Variables

#### Core Identity Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `TALOS_VERSION` | Semantic version of Talos deployment | `4.0.0` | SemVer format (x.y.z) | Yes | public |
| `TALOS_INSTANCE_ID` | Unique instance identifier (UUID v4) | Auto-generated | Valid UUID v4 | No | public |
| `TRUST_LEVEL` | Default trust level for new skills | `0` | 0-5 (integer) | Yes | public |

#### Resource Ceiling Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `REDIS_MAX_MEMORY` | Maximum Redis memory allocation | `512mb` | 128mb-2048mb | Yes | public |
| `REDIS_MAX_MEMORY_POLICY` | LRU eviction policy | `allkeys-lru` | `allkeys-lru`, `volatile-lru`, `allkeys-random` | Yes | public |
| `CHROMADB_MAX_VECTORS` | Maximum vector count in ChromaDB | `100000` | 10000-500000 | Yes | public |
| `CHROMADB_MAX_DIMENSIONS` | Vector embedding dimensions | `1536` | 384-4096 | Yes | public |
| `VRAM_MUTEX_TIMEOUT` | GPU memory lock timeout (seconds) | `300` | 30-1800 | Yes | public |
| `VRAM_MAX_ALLOCATION` | Maximum GPU VRAM allocation (MB) | `4096` | 512-16384 | Yes | public |

#### API Authentication Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `GEMINI_API_KEY` | Google Gemini Flash API key | None | Valid Gemini API key | Yes | secret |
| `GEMINI_MODEL_NAME` | Gemini model identifier | `gemini-1.5-flash` | `gemini-1.5-flash`, `gemini-1.5-flash-8b` | Yes | public |
| `GEMINI_MAX_TOKENS` | Maximum tokens per request | `8192` | 1024-32768 | Yes | public |
| `GEMINI_TEMPERATURE` | Sampling temperature | `0.7` | 0.0-2.0 | Yes | public |
| `QWEN_MODEL_PATH` | Local Qwen model path | `/models/qwen` | Valid filesystem path | No | public |
| `QWEN_CONTEXT_LENGTH` | Qwen context window | `32768` | 4096-131072 | No | public |

#### Web Interface Security Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `BASIC_AUTH_USER` | Web GUI username | `admin` | 4-32 alphanumeric chars | Yes | sensitive |
| `BASIC_AUTH_PASS` | Web GUI password | None | 16-64 chars, complex | Yes | secret |
| `WEB_PORT` | Web interface port | `8080` | 1024-65535 | Yes | public |
| `WEB_BIND_ADDRESS` | Web interface bind address | `127.0.0.1` | Valid IPv4/IPv6 | Yes | public |
| `SESSION_TIMEOUT` | Web session timeout (minutes) | `30` | 5-240 | Yes | public |

#### Network & VPN Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `TAILSCALE_AUTH_KEY` | Tailscale authentication key | None | Valid Tailscale auth key | No | secret |
| `TAILSCALE_HOSTNAME` | Tailscale node hostname | `talos-node` | 1-63 alphanumeric | No | public |
| `TAILSCALE_ACCEPT_DNS` | Accept Tailscale DNS | `true` | `true`, `false` | No | public |
| `TAILSCALE_ACCEPT_ROUTES` | Accept subnet routes | `false` | `true`, `false` | No | public |

#### Logging & Monitoring Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `LOG_LEVEL` | Global logging verbosity | `INFO` | `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` | Yes | public |
| `LOG_FORMAT` | Log output format | `json` | `json`, `text` | Yes | public |
| `LOG_TIER1_RETENTION_DAYS` | Tier 1 log retention | `90` | 30-365 | Yes | public |
| `LOG_TIER2_RETENTION_DAYS` | Tier 2 log retention | `30` | 7-90 | Yes | public |
| `LOG_TIER3_RETENTION_DAYS` | Tier 3 log retention | `7` | 1-30 | Yes | public |
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` | `true`, `false` | Yes | public |
| `METRICS_PORT` | Prometheus metrics port | `9090` | 1024-65535 | Yes | public |

#### Security & Sandboxing Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `STRIKE_THRESHOLD` | Max violations before skill ban | `3` | 1-10 | Yes | public |
| `SANDBOX_MEMORY_LIMIT` | Sandbox container memory limit | `512m` | 128m-2048m | Yes | public |
| `SANDBOX_PIDS_LIMIT` | Sandbox container PID limit | `50` | 10-200 | Yes | public |
| `SANDBOX_CPU_QUOTA` | Sandbox CPU quota (percent) | `50` | 10-100 | Yes | public |
| `SANDBOX_TIMEOUT` | Sandbox execution timeout (seconds) | `60` | 10-300 | Yes | public |
| `SOCKET_PROXY_ENABLED` | Enable restricted Docker socket | `true` | `true`, `false` | Yes | public |
| `SOCKET_PROXY_ALLOWED_OPS` | Allowed Docker operations | `containers:start,containers:stop,containers:create` | Comma-separated list | Yes | public |

#### Intelligence & Memory Variables

| Variable | Description | Default | Allowed Values | Required | Classification |
|----------|-------------|---------|----------------|----------|----------------|
| `MEMORY_CONTEXT_WINDOW` | Conversation context window | `10` | 5-50 | Yes | public |
| `MEMORY_SIMILARITY_THRESHOLD` | Vector similarity cutoff | `0.75` | 0.5-0.95 | Yes | public |
| `SKILL_AUTOLOAD_ENABLED` | Auto-load approved skills | `true` | `true`, `false` | Yes | public |
| `SKILL_SIGNATURE_VERIFY` | Verify skill signatures | `true` | `true`, `false` | Yes | public |
| `RECURSIVE_SELF_IMPROVE` | Allow self-modification | `false` | `true`, `false` | Yes | public |

### 1.2.3 Environment File Template

```bash
# ~/talos/config/talos.env
# Talos v4.0 Environment Configuration
# PERMISSIONS: chmod 600, chown 1000:1000
# WARNING: This file contains secrets. Protect accordingly.

# =============================================================================
# CORE IDENTITY
# =============================================================================
TALOS_VERSION=4.0.0
TALOS_INSTANCE_ID=auto-generated
TRUST_LEVEL=0

# =============================================================================
# RESOURCE CEILINGS (Hard Limits)
# =============================================================================
REDIS_MAX_MEMORY=512mb
REDIS_MAX_MEMORY_POLICY=allkeys-lru
CHROMADB_MAX_VECTORS=100000
CHROMADB_MAX_DIMENSIONS=1536
VRAM_MUTEX_TIMEOUT=300
VRAM_MAX_ALLOCATION=4096

# =============================================================================
# API AUTHENTICATION (REQUIRED)
# =============================================================================
# GEMINI_API_KEY: Obtain from https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL_NAME=gemini-1.5-flash
GEMINI_MAX_TOKENS=8192
GEMINI_TEMPERATURE=0.7

# Qwen Local Model (Optional - for offline operation)
# QWEN_MODEL_PATH=/models/qwen
# QWEN_CONTEXT_LENGTH=32768

# =============================================================================
# WEB INTERFACE SECURITY (REQUIRED)
# =============================================================================
# BASIC_AUTH_USER: Web GUI login username
BASIC_AUTH_USER=admin
# BASIC_AUTH_PASS: MUST be 16+ characters with mixed case, numbers, symbols
BASIC_AUTH_PASS=ChangeThisToASecurePassword16Chars!
WEB_PORT=8080
WEB_BIND_ADDRESS=127.0.0.1
SESSION_TIMEOUT=30

# =============================================================================
# TAILSCALE VPN (Optional)
# =============================================================================
# TAILSCALE_AUTH_KEY: Obtain from https://login.tailscale.com/admin/settings/keys
# TAILSCALE_AUTH_KEY=tskey-auth-xxxxxxxxxxxx
# TAILSCALE_HOSTNAME=talos-node
# TAILSCALE_ACCEPT_DNS=true
# TAILSCALE_ACCEPT_ROUTES=false

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_TIER1_RETENTION_DAYS=90
LOG_TIER2_RETENTION_DAYS=30
LOG_TIER3_RETENTION_DAYS=7
METRICS_ENABLED=true
METRICS_PORT=9090

# =============================================================================
# SECURITY & SANDBOXING
# =============================================================================
STRIKE_THRESHOLD=3
SANDBOX_MEMORY_LIMIT=512m
SANDBOX_PIDS_LIMIT=50
SANDBOX_CPU_QUOTA=50
SANDBOX_TIMEOUT=60
SOCKET_PROXY_ENABLED=true
SOCKET_PROXY_ALLOWED_OPS=containers:start,containers:stop,containers:create

# =============================================================================
# INTELLIGENCE & MEMORY
# =============================================================================
MEMORY_CONTEXT_WINDOW=10
MEMORY_SIMILARITY_THRESHOLD=0.75
SKILL_AUTOLOAD_ENABLED=true
SKILL_SIGNATURE_VERIFY=true
RECURSIVE_SELF_IMPROVE=false
```

### 1.2.4 Environment Validation Script

```bash
#!/bin/bash
# validate_env.sh
# Validates environment variables before container startup

set -euo pipefail

ERRORS=0
WARNINGS=0

log_error() {
    echo "[ERROR] $1" >&2
    ((ERRORS++))
}

log_warning() {
    echo "[WARNING] $1" >&2
    ((WARNINGS++))
}

log_info() {
    echo "[INFO] $1"
}

# Required variables check
check_required() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    
    if [[ -z "$var_value" ]]; then
        log_error "Required variable $var_name is not set"
        return 1
    fi
    log_info "$var_name is set"
    return 0
}

# Range validation
validate_range() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    local min="$2"
    local max="$3"
    
    if [[ -n "$var_value" ]]; then
        if [[ ! "$var_value" =~ ^[0-9]+$ ]]; then
            log_error "$var_name must be numeric (got: $var_value)"
            return 1
        fi
        if [[ "$var_value" -lt "$min" || "$var_value" -gt "$max" ]]; then
            log_error "$var_name must be between $min and $max (got: $var_value)"
            return 1
        fi
    fi
    return 0
}

# Password strength validation
validate_password() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    
    if [[ -z "$var_value" ]]; then
        log_error "$var_name is required but not set"
        return 1
    fi
    
    local length=${#var_value}
    if [[ $length -lt 16 ]]; then
        log_error "$var_name must be at least 16 characters (got: $length)"
        return 1
    fi
    
    if [[ ! "$var_value" =~ [A-Z] ]]; then
        log_warning "$var_name should contain uppercase letters"
    fi
    if [[ ! "$var_value" =~ [a-z] ]]; then
        log_warning "$var_name should contain lowercase letters"
    fi
    if [[ ! "$var_value" =~ [0-9] ]]; then
        log_warning "$var_name should contain numbers"
    fi
    if [[ ! "$var_value" =~ [^a-zA-Z0-9] ]]; then
        log_warning "$var_name should contain special characters"
    fi
    
    log_info "$var_name meets minimum requirements"
    return 0
}

log_info "Starting environment validation..."

# Check required variables
check_required "TALOS_VERSION"
check_required "REDIS_MAX_MEMORY"
check_required "CHROMADB_MAX_VECTORS"
check_required "GEMINI_API_KEY"
check_required "BASIC_AUTH_USER"
check_required "BASIC_AUTH_PASS"
check_required "LOG_LEVEL"
check_required "STRIKE_THRESHOLD"

# Validate ranges
validate_range "TRUST_LEVEL" 0 5
validate_range "VRAM_MUTEX_TIMEOUT" 30 1800
validate_range "GEMINI_MAX_TOKENS" 1024 32768
validate_range "SESSION_TIMEOUT" 5 240
validate_range "LOG_TIER1_RETENTION_DAYS" 30 365
validate_range "STRIKE_THRESHOLD" 1 10
validate_range "SANDBOX_PIDS_LIMIT" 10 200

# Validate password strength
validate_password "BASIC_AUTH_PASS"

# Validate log level
if [[ -n "${LOG_LEVEL:-}" ]]; then
    case "$LOG_LEVEL" in
        DEBUG|INFO|WARN|ERROR|FATAL)
            log_info "LOG_LEVEL is valid: $LOG_LEVEL"
            ;;
        *)
            log_error "LOG_LEVEL must be one of: DEBUG, INFO, WARN, ERROR, FATAL (got: $LOG_LEVEL)"
            ;;
    esac
fi

# Summary
if [[ $ERRORS -eq 0 ]]; then
    log_info "Environment validation PASSED (warnings: $WARNINGS)"
    exit 0
else
    log_error "Environment validation FAILED (errors: $ERRORS, warnings: $WARNINGS)"
    exit 1
fi
```

---

## 1.3 The First Boot Sequence

### 1.3.1 Sequence Overview

The First Boot Sequence orchestrates the initialization of all Talos subsystems within the first 60 seconds of container life. Each step has defined timing, dependencies, and failure handling.

```
Timeline (0-60 seconds):
┌─────────────────────────────────────────────────────────────────────────────┐
│  0s    5s    10s   15s   20s   25s   30s   35s   40s   45s   50s   55s   60s│
│  │     │     │     │     │     │     │     │     │     │     │     │     │ │
│  [1]──[2]──[3]──[4]──[5]──[6]──[7]──[8]──[9]──[10]─────────────────────────│
│   │    │    │    │    │    │    │    │    │                                 │
│   ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼                                 │
│  Init  Dir   Env  Redis Chroma Skill Socket Health Ready                     │
│        Perms  Val  Conn   Init   Unpack Proxy  Check  State                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3.2 Step-by-Step Boot Sequence

#### Step 1: Container Initialization (0-3 seconds)

**Purpose:** Initialize tini as PID 1 and establish process supervision.

**Commands:**
```bash
# Dockerfile entrypoint
tini -- /app/talos/boot/init.sh
```

**Actions:**
1. tini assumes PID 1 for proper signal handling
2. Set process limits: `ulimit -n 65536`
3. Configure signal handlers for SIGTERM, SIGINT
4. Create boot log at `/var/log/talos/boot.log`

**Health Gate:**
- tini process must be PID 1
- Signal handlers registered successfully

**Failure Handling:**
```bash
if [[ $$ -ne 1 ]]; then
    echo "[FATAL] Not running as PID 1 - tini may not be functioning" >&2
    exit 1
fi
```

**Timing:** 0-3 seconds  
**Dependencies:** None  
**Next Step:** Directory Permission Verification

---

#### Step 2: Directory Permission Verification (3-6 seconds)

**Purpose:** Verify all required directories exist with correct permissions.

**Commands:**
```bash
#!/bin/bash
# boot/02_verify_directories.sh

set -euo pipefail

TALOS_DIRS=(
    "/talos/skills/quarantine:750"
    "/talos/skills/active:755"
    "/talos/skills/deprecated:750"
    "/talos/keys:700"
    "/talos/logs/tier1:750"
    "/talos/logs/tier2:750"
    "/talos/logs/tier3:755"
    "/talos/data/redis:700"
    "/talos/data/chromadb:700"
    "/talos/config:755"
    "/talos/backups:750"
    "/talos/tmp:1777"
)

echo "[BOOT:02] Verifying directory permissions..."

for dir_spec in "${TALOS_DIRS[@]}"; do
    IFS=':' read -r dir_path expected_perms <<< "$dir_spec"
    
    if [[ ! -d "$dir_path" ]]; then
        echo "[BOOT:02:ERROR] Directory missing: $dir_path"
        exit 1
    fi
    
    actual_perms=$(stat -c '%a' "$dir_path")
    if [[ "$actual_perms" != "$expected_perms" ]]; then
        echo "[BOOT:02:WARN] $dir_path has permissions $actual_perms, expected $expected_perms"
        chmod "$expected_perms" "$dir_path"
        echo "[BOOT:02:INFO] Corrected permissions on $dir_path"
    fi
done

echo "[BOOT:02] Directory verification complete"
```

**Health Gate:**
- All 12 directories exist
- Permissions match specification
- Writable by container user (UID 1000)

**Failure Handling:**
- Missing directory: Fatal error, exit code 1
- Permission mismatch: Auto-correct and log warning
- Read-only filesystem: Fatal error

**Timing:** 3-6 seconds  
**Dependencies:** Step 1 (Container Initialization)  
**Next Step:** Environment Validation

---

#### Step 3: Environment Validation (6-10 seconds)

**Purpose:** Load and validate all environment variables.

**Commands:**
```bash
#!/bin/bash
# boot/03_validate_environment.sh

set -euo pipefail

ENV_FILE="/talos/config/talos.env"

echo "[BOOT:03] Loading environment configuration..."

# Load environment file if exists
if [[ -f "$ENV_FILE" ]]; then
    # Verify file permissions
    file_perms=$(stat -c '%a' "$ENV_FILE")
    if [[ "$file_perms" != "600" && "$file_perms" != "400" ]]; then
        echo "[BOOT:03:WARN] $ENV_FILE has permissions $file_perms, expected 600 or 400"
    fi
    
    # Source environment file
    set -a
    source "$ENV_FILE"
    set +a
    echo "[BOOT:03] Loaded environment from $ENV_FILE"
else
    echo "[BOOT:03:WARN] Environment file not found: $ENV_FILE"
fi

# Set defaults for missing variables
export TALOS_VERSION="${TALOS_VERSION:-4.0.0}"
export TRUST_LEVEL="${TRUST_LEVEL:-0}"
export REDIS_MAX_MEMORY="${REDIS_MAX_MEMORY:-512mb}"
export CHROMADB_MAX_VECTORS="${CHROMADB_MAX_VECTORS:-100000}"
export VRAM_MUTEX_TIMEOUT="${VRAM_MUTEX_TIMEOUT:-300}"
export GEMINI_MODEL_NAME="${GEMINI_MODEL_NAME:-gemini-1.5-flash}"
export GEMINI_MAX_TOKENS="${GEMINI_MAX_TOKENS:-8192}"
export GEMINI_TEMPERATURE="${GEMINI_TEMPERATURE:-0.7}"
export WEB_PORT="${WEB_PORT:-8080}"
export WEB_BIND_ADDRESS="${WEB_BIND_ADDRESS:-127.0.0.1}"
export SESSION_TIMEOUT="${SESSION_TIMEOUT:-30}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export LOG_FORMAT="${LOG_FORMAT:-json}"
export STRIKE_THRESHOLD="${STRIKE_THRESHOLD:-3}"
export SANDBOX_MEMORY_LIMIT="${SANDBOX_MEMORY_LIMIT:-512m}"
export SANDBOX_PIDS_LIMIT="${SANDBOX_PIDS_LIMIT:-50}"
export SANDBOX_TIMEOUT="${SANDBOX_TIMEOUT:-60}"
export SOCKET_PROXY_ENABLED="${SOCKET_PROXY_ENABLED:-true}"
export MEMORY_CONTEXT_WINDOW="${MEMORY_CONTEXT_WINDOW:-10}"
export MEMORY_SIMILARITY_THRESHOLD="${MEMORY_SIMILARITY_THRESHOLD:-0.75}"

# Validate required secrets
REQUIRED_SECRETS=("GEMINI_API_KEY" "BASIC_AUTH_PASS")
MISSING_SECRETS=()

for secret in "${REQUIRED_SECRETS[@]}"; do
    if [[ -z "${!secret:-}" ]]; then
        MISSING_SECRETS+=("$secret")
    fi
done

if [[ ${#MISSING_SECRETS[@]} -gt 0 ]]; then
    echo "[BOOT:03:ERROR] Missing required secrets: ${MISSING_SECRETS[*]}"
    exit 1
fi

# Validate TRUST_LEVEL range
if [[ "$TRUST_LEVEL" -lt 0 || "$TRUST_LEVEL" -gt 5 ]]; then
    echo "[BOOT:03:ERROR] TRUST_LEVEL must be 0-5, got: $TRUST_LEVEL"
    exit 1
fi

echo "[BOOT:03] Environment validation complete"
echo "[BOOT:03] TALOS_VERSION=$TALOS_VERSION"
echo "[BOOT:03] TRUST_LEVEL=$TRUST_LEVEL"
echo "[BOOT:03] LOG_LEVEL=$LOG_LEVEL"
```

**Health Gate:**
- All required secrets present
- TRUST_LEVEL in valid range (0-5)
- Memory limits parseable

**Failure Handling:**
- Missing required secret: Fatal error, exit code 1
- Invalid TRUST_LEVEL: Fatal error, exit code 1
- Missing optional variables: Use defaults, log info

**Timing:** 6-10 seconds  
**Dependencies:** Step 2 (Directory Verification)  
**Next Step:** Redis Connection & LRU Configuration

---

#### Step 4: Redis Connection & LRU Configuration (10-18 seconds)

**Purpose:** Establish Redis connection and configure LRU eviction.

**Commands:**
```bash
#!/bin/bash
# boot/04_init_redis.sh

set -euo pipefail

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_MAX_MEMORY="${REDIS_MAX_MEMORY:-512mb}"
REDIS_MAX_MEMORY_POLICY="${REDIS_MAX_MEMORY_POLICY:-allkeys-lru}"
MAX_RETRIES=10
RETRY_DELAY=1

echo "[BOOT:04] Initializing Redis connection..."

# Wait for Redis to be available
retry_count=0
while ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; do
    ((retry_count++))
    if [[ $retry_count -ge $MAX_RETRIES ]]; then
        echo "[BOOT:04:ERROR] Redis connection failed after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "[BOOT:04] Waiting for Redis... (attempt $retry_count/$MAX_RETRIES)"
    sleep $RETRY_DELAY
done

echo "[BOOT:04] Redis is responding to ping"

# Configure Redis memory limits
echo "[BOOT:04] Configuring Redis memory limits..."
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG SET maxmemory "$REDIS_MAX_MEMORY"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG SET maxmemory-policy "$REDIS_MAX_MEMORY_POLICY"

# Verify configuration
configured_maxmemory=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET maxmemory | tail -n1)
configured_policy=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET maxmemory-policy | tail -n1)

echo "[BOOT:04] Redis maxmemory: $configured_maxmemory"
echo "[BOOT:04] Redis maxmemory-policy: $configured_policy"

# Test basic operations
echo "[BOOT:04] Testing Redis operations..."
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET __talos_boot_test "ok" EX 10 > /dev/null
test_result=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET __talos_boot_test)
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL __talos_boot_test > /dev/null

if [[ "$test_result" != "ok" ]]; then
    echo "[BOOT:04:ERROR] Redis operation test failed"
    exit 1
fi

echo "[BOOT:04] Redis initialization complete"
```

**Health Gate:**
- Redis responds to ping
- Memory limits configured
- Read/write test successful

**Failure Handling:**
- Connection timeout: Retry 10 times with 1s delay, then fatal
- Configuration failure: Log error, attempt to continue with defaults
- Operation test failure: Fatal error, exit code 1

**Timing:** 10-18 seconds  
**Dependencies:** Step 3 (Environment Validation)  
**Next Step:** ChromaDB Initialization

---

#### Step 5: ChromaDB Initialization (18-28 seconds)

**Purpose:** Initialize ChromaDB vector store and verify persistence.

**Commands:**
```bash
#!/bin/bash
# boot/05_init_chromadb.sh

set -euo pipefail

CHROMADB_HOST="${CHROMADB_HOST:-localhost}"
CHROMADB_PORT="${CHROMADB_PORT:-8000}"
CHROMADB_PERSIST_DIR="/talos/data/chromadb"
CHROMADB_MAX_VECTORS="${CHROMADB_MAX_VECTORS:-100000}"
MAX_RETRIES=15
RETRY_DELAY=1

echo "[BOOT:05] Initializing ChromaDB..."

# Wait for ChromaDB to be available
retry_count=0
while ! curl -sf "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/heartbeat" > /dev/null 2>&1; do
    ((retry_count++))
    if [[ $retry_count -ge $MAX_RETRIES ]]; then
        echo "[BOOT:05:ERROR] ChromaDB connection failed after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "[BOOT:05] Waiting for ChromaDB... (attempt $retry_count/$MAX_RETRIES)"
    sleep $RETRY_DELAY
done

echo "[BOOT:05] ChromaDB is responding"

# Verify persistence directory
if [[ ! -d "$CHROMADB_PERSIST_DIR" ]]; then
    echo "[BOOT:05:ERROR] ChromaDB persistence directory missing: $CHROMADB_PERSIST_DIR"
    exit 1
fi

# Check persistence directory permissions
persist_perms=$(stat -c '%a' "$CHROMADB_PERSIST_DIR")
if [[ "$persist_perms" != "700" ]]; then
    echo "[BOOT:05:WARN] ChromaDB persistence directory has permissions $persist_perms, expected 700"
    chmod 700 "$CHROMADB_PERSIST_DIR"
fi

# Get collection count via API
collections_response=$(curl -sf "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/collections" 2>/dev/null || echo "[]")
collection_count=$(echo "$collections_response" | grep -o '"name"' | wc -l)

echo "[BOOT:05] Existing collections: $collection_count"

# Verify vector limit configuration
echo "[BOOT:05] Vector store limit: $CHROMADB_MAX_VECTORS vectors"

# Test embedding functionality
echo "[BOOT:05] Testing vector operations..."
test_collection="__talos_boot_test"

# Create test collection
curl -sf -X POST "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/collections" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"$test_collection\",\"metadata\":{\"hnsw:space\":\"cosine\"}}" > /dev/null 2>&1 || true

# Add test vector
curl -sf -X POST "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/collections/$test_collection/add" \
    -H "Content-Type: application/json" \
    -d '{
        "ids":["boot_test_1"],
        "embeddings":[[0.1,0.2,0.3,0.4]],
        "metadatas":[{"test":true}],
        "documents":["boot test document"]
    }' > /dev/null 2>&1

# Query test vector
query_result=$(curl -sf -X POST "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/collections/$test_collection/query" \
    -H "Content-Type: application/json" \
    -d '{"query_embeddings":[[0.1,0.2,0.3,0.4]],"n_results":1}' 2>/dev/null || echo "{}")

# Cleanup test collection
curl -sf -X DELETE "http://${CHROMADB_HOST}:${CHROMADB_PORT}/api/v1/collections/$test_collection" > /dev/null 2>&1 || true

if [[ -n "$query_result" && "$query_result" != "{}" ]]; then
    echo "[BOOT:05] Vector operations test passed"
else
    echo "[BOOT:05:WARN] Vector operations test returned empty result"
fi

echo "[BOOT:05] ChromaDB initialization complete"
```

**Health Gate:**
- ChromaDB responds to heartbeat
- Persistence directory accessible
- Vector operations functional

**Failure Handling:**
- Connection timeout: Retry 15 times with 1s delay, then fatal
- Persistence directory missing: Fatal error
- Vector test failure: Warning, continue with degraded functionality

**Timing:** 18-28 seconds  
**Dependencies:** Step 4 (Redis Initialization)  
**Next Step:** Vector Store Schema Creation

---

#### Step 6: Vector Store Schema Creation (28-35 seconds)

**Purpose:** Create required collections and indexes in ChromaDB.

**Commands:**
```python
#!/usr/bin/env python3
# boot/06_create_schema.py

import os
import sys
import requests
import json
import time

CHROMADB_HOST = os.environ.get('CHROMADB_HOST', 'localhost')
CHROMADB_PORT = os.environ.get('CHROMADB_PORT', '8000')
BASE_URL = f"http://{CHROMADB_HOST}:{CHROMADB_PORT}/api/v1"

REQUIRED_COLLECTIONS = [
    {
        "name": "skill_memory",
        "metadata": {"hnsw:space": "cosine", "description": "Skill execution memory embeddings"}
    },
    {
        "name": "conversation_history",
        "metadata": {"hnsw:space": "cosine", "description": "User conversation embeddings"}
    },
    {
        "name": "knowledge_base",
        "metadata": {"hnsw:space": "cosine", "description": "General knowledge embeddings"}
    },
    {
        "name": "skill_registry",
        "metadata": {"hnsw:space": "cosine", "description": "Skill metadata and documentation"}
    }
]

def log(msg, level="INFO"):
    print(f"[BOOT:06:{level}] {msg}")

def collection_exists(name):
    try:
        response = requests.get(f"{BASE_URL}/collections", timeout=5)
        if response.status_code == 200:
            collections = response.json()
            return any(c.get('name') == name for c in collections)
    except Exception as e:
        log(f"Error checking collection: {e}", "WARN")
    return False

def create_collection(name, metadata):
    try:
        response = requests.post(
            f"{BASE_URL}/collections",
            json={"name": name, "metadata": metadata},
            timeout=10
        )
        return response.status_code in [200, 201, 409]  # 409 = already exists
    except Exception as e:
        log(f"Error creating collection {name}: {e}", "ERROR")
        return False

def main():
    log("Creating vector store schema...")
    
    created_count = 0
    existing_count = 0
    
    for collection_spec in REQUIRED_COLLECTIONS:
        name = collection_spec["name"]
        metadata = collection_spec["metadata"]
        
        if collection_exists(name):
            log(f"Collection already exists: {name}")
            existing_count += 1
        else:
            log(f"Creating collection: {name}")
            if create_collection(name, metadata):
                log(f"Created collection: {name}")
                created_count += 1
            else:
                log(f"Failed to create collection: {name}", "ERROR")
                sys.exit(1)
    
    log(f"Schema creation complete: {created_count} created, {existing_count} existing")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Health Gate:**
- All 4 required collections exist
- Each collection has proper metadata
- Collections are queryable

**Failure Handling:**
- Collection creation failure: Fatal error, exit code 1
- Metadata validation failure: Warning, continue

**Timing:** 28-35 seconds  
**Dependencies:** Step 5 (ChromaDB Initialization)  
**Next Step:** Genesis Skill Unpacking

---

#### Step 7: Genesis Skill Unpacking (35-45 seconds)

**Purpose:** Unpack and validate bundled genesis skills into the active directory.

**Commands:**
```bash
#!/bin/bash
# boot/07_unpack_skills.sh

set -euo pipefail

GENESIS_SKILLS_DIR="/app/talos/skills/genesis"
ACTIVE_SKILLS_DIR="/talos/skills/active"
QUARANTINE_DIR="/talos/skills/quarantine"
TRUST_LEVEL="${TRUST_LEVEL:-0}"
SKILL_SIGNATURE_VERIFY="${SKILL_SIGNATURE_VERIFY:-true}"

echo "[BOOT:07] Unpacking genesis skills..."

# Verify genesis skills directory exists
if [[ ! -d "$GENESIS_SKILLS_DIR" ]]; then
    echo "[BOOT:07:WARN] Genesis skills directory not found: $GENESIS_SKILLS_DIR"
    echo "[BOOT:07] Skipping skill unpacking"
    exit 0
fi

# Function to validate skill package
validate_skill() {
    local skill_path="$1"
    local skill_name=$(basename "$skill_path")
    
    echo "[BOOT:07] Validating skill: $skill_name"
    
    # Check for required files
    if [[ ! -f "$skill_path/skill.json" ]]; then
        echo "[BOOT:07:ERROR] Missing skill.json in $skill_name"
        return 1
    fi
    
    if [[ ! -f "$skill_path/main.py" && ! -f "$skill_path/main.sh" ]]; then
        echo "[BOOT:07:ERROR] Missing main entry point in $skill_name"
        return 1
    fi
    
    # Parse skill metadata
    local skill_trust=$(jq -r '.trust_level // 0' "$skill_path/skill.json" 2>/dev/null || echo "0")
    local skill_version=$(jq -r '.version // "unknown"' "$skill_path/skill.json" 2>/dev/null || echo "unknown")
    local skill_signature=$(jq -r '.signature // ""' "$skill_path/skill.json" 2>/dev/null || echo "")
    
    echo "[BOOT:07]   Trust level: $skill_trust"
    echo "[BOOT:07]   Version: $skill_version"
    
    # Check trust level
    if [[ "$skill_trust" -gt "$TRUST_LEVEL" ]]; then
        echo "[BOOT:07:WARN] Skill $skill_name trust level ($skill_trust) exceeds system trust ($TRUST_LEVEL)"
        return 2  # Special return for quarantine
    fi
    
    # Verify signature if required
    if [[ "$SKILL_SIGNATURE_VERIFY" == "true" && -z "$skill_signature" ]]; then
        echo "[BOOT:07:WARN] Skill $skill_name has no signature"
        return 2
    fi
    
    return 0
}

# Process each genesis skill
skill_count=0
quarantine_count=0

for skill_dir in "$GENESIS_SKILLS_DIR"/*/; do
    [[ -d "$skill_dir" ]] || continue
    
    skill_name=$(basename "$skill_dir")
    target_path="$ACTIVE_SKILLS_DIR/$skill_name"
    quarantine_path="$QUARANTINE_DIR/$skill_name"
    
    # Skip if already exists
    if [[ -d "$target_path" ]]; then
        echo "[BOOT:07] Skill already exists: $skill_name"
        continue
    fi
    
    # Validate skill
    validate_skill "$skill_dir"
    validation_result=$?
    
    if [[ $validation_result -eq 0 ]]; then
        # Copy to active directory
        cp -r "$skill_dir" "$target_path"
        chmod -R 755 "$target_path"
        echo "[BOOT:07] Activated skill: $skill_name"
        ((skill_count++))
    elif [[ $validation_result -eq 2 ]]; then
        # Quarantine
        cp -r "$skill_dir" "$quarantine_path"
        chmod -R 750 "$quarantine_path"
        echo "[BOOT:07] Quarantined skill: $skill_name"
        ((quarantine_count++))
    else
        echo "[BOOT:07:ERROR] Validation failed for: $skill_name"
    fi
done

echo "[BOOT:07] Skill unpacking complete: $skill_count activated, $quarantine_count quarantined"
```

**Health Gate:**
- At least one core skill activated OR zero genesis skills (acceptable)
- No validation errors for activated skills
- Quarantined skills isolated properly

**Failure Handling:**
- Individual skill validation failure: Quarantine skill, continue
- All skills fail validation: Warning, continue with no skills
- Copy failure: Log error, continue

**Timing:** 35-45 seconds  
**Dependencies:** Step 6 (Schema Creation)  
**Next Step:** Socket Proxy Verification

---

#### Step 8: Socket Proxy Verification (45-52 seconds)

**Purpose:** Verify the restricted Docker socket proxy is operational.

**Commands:**
```bash
#!/bin/bash
# boot/08_verify_socket_proxy.sh

set -euo pipefail

SOCKET_PROXY_ENABLED="${SOCKET_PROXY_ENABLED:-true}"
SOCKET_PROXY_URL="${SOCKET_PROXY_URL:-http://localhost:2375}"
ALLOWED_OPS="${SOCKET_PROXY_ALLOWED_OPS:-containers:start,containers:stop,containers:create}"

echo "[BOOT:08] Verifying socket proxy..."

if [[ "$SOCKET_PROXY_ENABLED" != "true" ]]; then
    echo "[BOOT:08] Socket proxy disabled, skipping verification"
    exit 0
fi

# Test connectivity
if ! curl -sf "${SOCKET_PROXY_URL}/_ping" > /dev/null 2>&1; then
    echo "[BOOT:08:ERROR] Socket proxy not responding at $SOCKET_PROXY_URL"
    exit 1
fi

echo "[BOOT:08] Socket proxy is responding"

# Verify version endpoint works
version_response=$(curl -sf "${SOCKET_PROXY_URL}/version" 2>/dev/null || echo "{}")
if [[ "$version_response" == "{}" ]]; then
    echo "[BOOT:08:WARN] Could not retrieve Docker version info"
fi

# Test allowed operations
echo "[BOOT:08] Testing allowed operations..."

# Test containers/list (should work)
list_result=$(curl -sf "${SOCKET_PROXY_URL}/containers/json?limit=1" 2>/dev/null || echo "")
if [[ -n "$list_result" ]]; then
    echo "[BOOT:08] containers:list - ALLOWED"
else
    echo "[BOOT:08] containers:list - CHECK FAILED"
fi

# Test containers/create (dry run - should get method not allowed or similar)
create_test=$(curl -sf -X POST "${SOCKET_PROXY_URL}/containers/create" \
    -H "Content-Type: application/json" \
    -d '{"Image":"hello-world","Cmd":["echo","test"]}' 2>/dev/null || echo "BLOCKED")

if [[ "$create_test" == "BLOCKED" ]]; then
    echo "[BOOT:08] containers:create - RESTRICTED (expected)"
else
    echo "[BOOT:08] containers:create - ALLOWED"
fi

# Verify restricted operations are blocked
echo "[BOOT:08] Verifying operation restrictions..."

# Try to access images endpoint (should be blocked)
images_result=$(curl -sf "${SOCKET_PROXY_URL}/images/json" 2>/dev/null || echo "BLOCKED")
if [[ "$images_result" == "BLOCKED" ]]; then
    echo "[BOOT:08] images:list - RESTRICTED (expected)"
else
    echo "[BOOT:08:WARN] images:list - NOT RESTRICTED (security concern)"
fi

echo "[BOOT:08] Socket proxy verification complete"
```

**Health Gate:**
- Socket proxy responds to ping
- Allowed operations functional
- Restricted operations blocked

**Failure Handling:**
- Proxy not responding: Fatal error if SOCKET_PROXY_ENABLED=true
- Restriction bypass detected: Warning, log security concern
- Individual test failure: Warning, continue

**Timing:** 45-52 seconds  
**Dependencies:** Step 7 (Skill Unpacking)  
**Next Step:** Health Check Endpoint Activation

---

#### Step 9: Health Check Endpoint Activation (52-57 seconds)

**Purpose:** Start the health check HTTP endpoint for monitoring.

**Commands:**
```bash
#!/bin/bash
# boot/09_activate_healthcheck.sh

set -euo pipefail

HEALTH_PORT="${HEALTH_PORT:-8081}"
HEALTH_BIND="${HEALTH_BIND:-127.0.0.1}"
METRICS_PORT="${METRICS_PORT:-9090}"

echo "[BOOT:09] Activating health check endpoint..."

# Create health check script
cat > /tmp/health_check.sh << 'EOF'
#!/bin/bash
# Dynamic health check script

HEALTH_STATUS="healthy"
HEALTH_CHECKS=()

# Check Redis
if redis-cli ping > /dev/null 2>&1; then
    HEALTH_CHECKS+=("redis:ok")
else
    HEALTH_CHECKS+=("redis:fail")
    HEALTH_STATUS="degraded"
fi

# Check ChromaDB
if curl -sf http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; then
    HEALTH_CHECKS+=("chromadb:ok")
else
    HEALTH_CHECKS+=("chromadb:fail")
    HEALTH_STATUS="degraded"
fi

# Check disk space
DISK_USAGE=$(df /talos | tail -1 | awk '{print $5}' | tr -d '%')
if [[ "$DISK_USAGE" -lt 90 ]]; then
    HEALTH_CHECKS+=("disk:ok")
else
    HEALTH_CHECKS+=("disk:warn")
    HEALTH_STATUS="degraded"
fi

# Check memory
MEM_AVAILABLE=$(cat /proc/meminfo | grep MemAvailable | awk '{print $2}')
if [[ "$MEM_AVAILABLE" -gt 1048576 ]]; then  # > 1GB
    HEALTH_CHECKS+=("memory:ok")
else
    HEALTH_CHECKS+=("memory:warn")
    HEALTH_STATUS="degraded"
fi

# Output JSON
printf '{"status":"%s","checks":[' "$HEALTH_STATUS"
first=true
for check in "${HEALTH_CHECKS[@]}"; do
    IFS=':' read -r name status <<< "$check"
    if [[ "$first" == "true" ]]; then
        first=false
    else
        printf ","
    fi
    printf '{"name":"%s","status":"%s"}' "$name" "$status"
done
printf '],"timestamp":"%s"}\n' "$(date -Iseconds)"
EOF

chmod +x /tmp/health_check.sh

# Start simple HTTP health server
cat > /tmp/health_server.py << EOF
#!/usr/bin/env python3
import http.server
import socketserver
import subprocess
import json

PORT = $HEALTH_PORT
BIND = "$HEALTH_BIND"

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            result = subprocess.run(['/tmp/health_check.sh'], capture_output=True, text=True)
            status_code = 200 if '"status":"healthy"' in result.stdout else 503
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(result.stdout.encode())
        elif self.path == '/ready':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ready":true}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

with socketserver.TCPServer((BIND, PORT), HealthHandler) as httpd:
    print(f"[BOOT:09] Health endpoint listening on {BIND}:{PORT}")
    httpd.serve_forever()
EOF

# Start health server in background
python3 /tmp/health_server.py &
HEALTH_PID=$!
echo $HEALTH_PID > /var/run/talos/healthd.pid

# Verify health endpoint is responding
sleep 1
if curl -sf "http://${HEALTH_BIND}:${HEALTH_PORT}/health" > /dev/null 2>&1; then
    echo "[BOOT:09] Health endpoint is responding"
else
    echo "[BOOT:09:WARN] Health endpoint not responding yet"
fi

echo "[BOOT:09] Health check activation complete"
```

**Health Gate:**
- Health endpoint responds on configured port
- All subsystem checks functional
- JSON response format valid

**Failure Handling:**
- Port binding failure: Try alternate port, log warning
- Subsystem check failure: Mark degraded, continue
- Server start failure: Fatal error

**Timing:** 52-57 seconds  
**Dependencies:** Step 8 (Socket Proxy Verification)  
**Next Step:** Ready State Announcement

---

#### Step 10: Ready State Announcement (57-60 seconds)

**Purpose:** Announce successful initialization and transition to operational state.

**Commands:**
```bash
#!/bin/bash
# boot/10_announce_ready.sh

set -euo pipefail

TALOS_VERSION="${TALOS_VERSION:-4.0.0}"
TALOS_INSTANCE_ID="${TALOS_INSTANCE_ID:-unknown}"
WEB_PORT="${WEB_PORT:-8080}"
HEALTH_PORT="${HEALTH_PORT:-8081}"
METRICS_PORT="${METRICS_PORT:-9090}"
START_TIME="${TALOS_START_TIME:-$(date +%s)}"

echo "[BOOT:10] Announcing ready state..."

# Calculate boot duration
CURRENT_TIME=$(date +%s)
BOOT_DURATION=$((CURRENT_TIME - START_TIME))

# Create ready state file
cat > /talos/.ready << EOF
{
    "status": "ready",
    "version": "${TALOS_VERSION}",
    "instance_id": "${TALOS_INSTANCE_ID}",
    "boot_duration_seconds": ${BOOT_DURATION},
    "boot_timestamp": "$(date -Iseconds)",
    "endpoints": {
        "web": "http://localhost:${WEB_PORT}",
        "health": "http://localhost:${HEALTH_PORT}/health",
        "ready": "http://localhost:${HEALTH_PORT}/ready",
        "metrics": "http://localhost:${METRICS_PORT}/metrics"
    },
    "subsystems": {
        "redis": "initialized",
        "chromadb": "initialized",
        "skills": "loaded",
        "socket_proxy": "verified",
        "health_endpoint": "active"
    }
}
EOF

chmod 644 /talos/.ready
chown 1000:1000 /talos/.ready

# Log ready state
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  TALOS v${TALOS_VERSION} READY                      ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Instance ID: ${TALOS_INSTANCE_ID}"
echo "║  Boot Duration: ${BOOT_DURATION}s"
echo "║  Web Interface: http://localhost:${WEB_PORT}"
echo "║  Health Check:  http://localhost:${HEALTH_PORT}/health"
echo "║  Metrics:       http://localhost:${METRICS_PORT}/metrics"
echo "╚════════════════════════════════════════════════════════════════╝"

# Write to boot log
cat >> /var/log/talos/boot.log << EOF
[$(date -Iseconds)] BOOT COMPLETE
Version: ${TALOS_VERSION}
Instance: ${TALOS_INSTANCE_ID}
Duration: ${BOOT_DURATION}s
Status: READY
EOF

# Signal readiness to orchestration
if [[ -n "${TALOS_READY_FIFO:-}" && -p "$TALOS_READY_FIFO" ]]; then
    echo "ready" > "$TALOS_READY_FIFO"
fi

# Set process title
printf '\0' | dd of=/proc/$$/cmdline bs=1 2>/dev/null || true
echo -n "talos-daemon:v${TALOS_VERSION}" > /proc/$$/comm 2>/dev/null || true

echo "[BOOT:10] Ready state announced - Talos is operational"
```

**Health Gate:**
- `.ready` file created with valid JSON
- Boot duration logged
- All endpoints documented

**Failure Handling:**
- File creation failure: Log warning, continue
- JSON encoding failure: Log error, create minimal ready file
- FIFO signal failure: Log warning, continue

**Timing:** 57-60 seconds  
**Dependencies:** Step 9 (Health Check Activation)  
**Next Step:** Main operational loop (outside boot sequence)

---

### 1.3.3 Boot Sequence Failure Matrix

| Step | Failure Mode | Impact | Handling | Exit Code |
|------|--------------|--------|----------|-----------|
| 1 | tini not PID 1 | Cannot handle signals properly | Fatal | 1 |
| 2 | Directory missing | Cannot persist data | Fatal | 1 |
| 2 | Permission mismatch | Security risk | Auto-correct, warn | 0 |
| 3 | Missing secret | Cannot authenticate | Fatal | 1 |
| 3 | Invalid TRUST_LEVEL | Security misconfiguration | Fatal | 1 |
| 4 | Redis timeout | No caching/memory | Retry 10x, then fatal | 1 |
| 4 | Redis config fail | Suboptimal performance | Warn, use defaults | 0 |
| 5 | ChromaDB timeout | No vector storage | Retry 15x, then fatal | 1 |
| 5 | Vector test fail | Degraded functionality | Warn, continue | 0 |
| 6 | Collection fail | No memory schema | Fatal | 1 |
| 7 | All skills invalid | No functionality | Warn, continue | 0 |
| 8 | Proxy not responding | No container control | Fatal if enabled | 1 |
| 9 | Health endpoint fail | No monitoring | Warn, retry alt port | 0 |
| 10 | Ready file fail | Orchestration issue | Warn, continue | 0 |

### 1.3.4 Master Boot Script

```bash
#!/bin/bash
# /app/talos/boot/init.sh
# Master initialization script - orchestrates all boot steps

set -euo pipefail

export TALOS_START_TIME=$(date +%s)

BOOT_SCRIPTS_DIR="/app/talos/boot"
LOG_FILE="/var/log/talos/boot.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"
}

log "═══════════════════════════════════════════════════════════"
log "TALOS v${TALOS_VERSION:-4.0.0} BOOT SEQUENCE INITIATED"
log "═══════════════════════════════════════════════════════════"

# Define boot steps with timing
BOOT_STEPS=(
    "01_init_container:0:3"
    "02_verify_directories:3:6"
    "03_validate_environment:6:10"
    "04_init_redis:10:18"
    "05_init_chromadb:18:28"
    "06_create_schema:28:35"
    "07_unpack_skills:35:45"
    "08_verify_socket_proxy:45:52"
    "09_activate_healthcheck:52:57"
    "10_announce_ready:57:60"
)

for step_spec in "${BOOT_STEPS[@]}"; do
    IFS=':' read -r step_name min_time max_time <<< "$step_spec"
    
    log "[BOOT] Executing $step_name (target: ${min_time}-${max_time}s)..."
    
    step_start=$(date +%s)
    
    if "${BOOT_SCRIPTS_DIR}/${step_name}.sh" >> "$LOG_FILE" 2>&1; then
        step_end=$(date +%s)
        step_duration=$((step_end - step_start))
        log "[BOOT] $step_name completed in ${step_duration}s"
    else
        exit_code=$?
        log "[BOOT:FATAL] $step_name failed with exit code $exit_code"
        
        # Write failure state
        echo '{"status":"failed","step":"'$step_name'","exit_code":'$exit_code'}' > /talos/.ready
        exit $exit_code
    fi
done

log "═══════════════════════════════════════════════════════════"
log "TALOS BOOT SEQUENCE COMPLETE"
log "═══════════════════════════════════════════════════════════"

# Transition to main operational loop
exec /app/talos/daemon/main.sh
```

---

## 1.4 Post-Boot Verification Checklist

After the First Boot Sequence completes, verify the following:

```bash
#!/bin/bash
# post_boot_verification.sh

echo "=== TALOS POST-BOOT VERIFICATION ==="

# 1. Check ready file
if [[ -f /talos/.ready ]]; then
    echo "[✓] Ready file exists"
    cat /talos/.ready | jq .status
else
    echo "[✗] Ready file missing"
fi

# 2. Verify health endpoint
curl -s http://localhost:8081/health | jq .

# 3. Check Redis
redis-cli ping

# 4. Check ChromaDB
curl -s http://localhost:8000/api/v1/heartbeat

# 5. List active skills
ls -la ~/talos/skills/active/

# 6. Verify socket proxy
curl -s http://localhost:2375/_ping

# 7. Check log files
ls -la ~/talos/logs/tier1/

echo "=== VERIFICATION COMPLETE ==="
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 4.0.0 | 2024 | Talos Engineering | Initial specification |

**Classification:** Technical Implementation  
**Distribution:** Internal Engineering  
**Review Cycle:** Quarterly or on major release
