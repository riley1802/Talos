# SECTION 4: Maintainability & Disaster Recovery (The Black Box)

**Document Version:** 4.0  
**Classification:** OPERATIONAL CRITICAL  
**Last Updated:** 2024  
**Purpose:** 3 AM emergency recovery procedures and operational observability

---

## 4.1 Logging Schema

### 4.1.1 Overview

Talos implements a three-tier logging system with strict retention policies:

| Tier | Type | Retention | Purpose |
|------|------|-----------|---------|
| Tier 1 | Audit | Indefinite | Security events, configuration changes |
| Tier 2 | Ops | 50MB Ring Buffer | Operational health, errors |
| Tier 3 | Debug | 50MB Ring Buffer | Detailed debugging information |

**Log Rotation:** File size-based (10MB max), NOT time-based  
**Format:** Structured JSON for machine parsing  
**Transport:** stdout/stderr for container environments

---

### 4.1.2 Tier 2 (Ops) Log Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "talos-log-tier2-ops",
  "title": "Talos Tier 2 Operational Log Schema",
  "description": "Schema for operational logs - 50MB ring buffer retention",
  "type": "object",
  "required": ["timestamp", "level", "component", "message", "correlation_id"],
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp with millisecond precision"
    },
    "level": {
      "type": "string",
      "enum": ["ERROR", "WARN", "INFO"],
      "description": "Log level - Tier 2 excludes DEBUG"
    },
    "component": {
      "type": "string",
      "enum": [
        "orchestrator",
        "process_supervisor",
        "health_check",
        "web_gui",
        "config_manager",
        "state_manager",
        "backup_service",
        "watchdog"
      ],
      "description": "System component generating the log"
    },
    "message": {
      "type": "string",
      "maxLength": 1000,
      "description": "Human-readable log message"
    },
    "correlation_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{16}$",
      "description": "16-character hex correlation ID for request tracing"
    },
    "context": {
      "type": "object",
      "description": "Request context for tracing",
      "properties": {
        "request_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{16}$"
        },
        "session_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{32}$"
        },
        "user_id": {
          "type": "string",
          "description": "Authenticated user identifier if applicable"
        },
        "source_ip": {
          "type": "string",
          "format": "ipv4"
        }
      }
    },
    "metadata": {
      "type": "object",
      "description": "Component-specific metadata",
      "properties": {
        "pid": {
          "type": "integer",
          "description": "Process ID when applicable"
        },
        "thread_id": {
          "type": "string",
          "description": "Thread identifier"
        },
        "duration_ms": {
          "type": "number",
          "description": "Operation duration in milliseconds"
        },
        "memory_mb": {
          "type": "number",
          "description": "Memory usage at log time"
        }
      }
    },
    "error": {
      "type": "object",
      "description": "Error details when level is ERROR or WARN",
      "properties": {
        "code": {
          "type": "string",
          "pattern": "^T[0-9]{3}$",
          "description": "Talos error code (T001-T999)"
        },
        "type": {
          "type": "string",
          "description": "Exception type or error category"
        },
        "stack_trace": {
          "type": "string",
          "description": "Condensed stack trace (max 10 frames)"
        },
        "recoverable": {
          "type": "boolean",
          "description": "Whether error is recoverable"
        }
      }
    }
  },
  "additionalProperties": false
}
```

**Tier 2 Example Log Entries:**

```json
{
  "timestamp": "2024-01-15T08:23:47.123Z",
  "level": "INFO",
  "component": "orchestrator",
  "message": "Task execution completed successfully",
  "correlation_id": "a1b2c3d4e5f67890",
  "context": {
    "request_id": "a1b2c3d4e5f67890",
    "session_id": "deadbeef1234567890abcdef12345678",
    "user_id": "admin"
  },
  "metadata": {
    "duration_ms": 145.2,
    "memory_mb": 128.5
  }
}
```

```json
{
  "timestamp": "2024-01-15T08:24:12.456Z",
  "level": "ERROR",
  "component": "health_check",
  "message": "Event loop blocked for 35 seconds",
  "correlation_id": "f9e8d7c6b5a41234",
  "context": {
    "request_id": "f9e8d7c6b5a41234"
  },
  "error": {
    "code": "T007",
    "type": "EventLoopBlocked",
    "recoverable": false
  }
}
```

---

### 4.1.3 Tier 3 (Debug) Log Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "talos-log-tier3-debug",
  "title": "Talos Tier 3 Debug Log Schema",
  "description": "Schema for debug logs - 50MB ring buffer retention",
  "type": "object",
  "required": ["timestamp", "level", "component", "message", "correlation_id"],
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "level": {
      "type": "string",
      "enum": ["DEBUG", "TRACE"],
      "description": "Debug log levels only"
    },
    "component": {
      "type": "string",
      "enum": [
        "orchestrator",
        "process_supervisor",
        "health_check",
        "web_gui",
        "config_manager",
        "state_manager",
        "backup_service",
        "watchdog",
        "event_loop",
        "task_executor",
        "llm_client"
      ]
    },
    "message": {
      "type": "string",
      "maxLength": 2000
    },
    "correlation_id": {
      "type": "string",
      "pattern": "^[a-f0-9]{16}$"
    },
    "context": {
      "type": "object",
      "properties": {
        "request_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{16}$"
        },
        "parent_correlation_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{16}$",
          "description": "Parent request for nested operations"
        },
        "call_depth": {
          "type": "integer",
          "minimum": 0,
          "description": "Nesting depth of operation"
        },
        "function_name": {
          "type": "string",
          "description": "Function or method name"
        },
        "line_number": {
          "type": "integer",
          "description": "Source code line number"
        },
        "file_path": {
          "type": "string",
          "description": "Relative source file path"
        }
      }
    },
    "payload": {
      "type": "object",
      "description": "Debug payload - may contain sensitive data",
      "properties": {
        "input_params": {
          "type": "object",
          "description": "Function input parameters (sanitized)"
        },
        "intermediate_state": {
          "type": "object",
          "description": "Intermediate computation state"
        },
        "raw_response": {
          "type": "string",
          "maxLength": 10000,
          "description": "Raw response data (truncated if needed)"
        }
      }
    },
    "performance": {
      "type": "object",
      "description": "Detailed performance metrics",
      "properties": {
        "cpu_percent": {
          "type": "number"
        },
        "memory_rss_mb": {
          "type": "number"
        },
        "memory_vms_mb": {
          "type": "number"
        },
        "io_read_bytes": {
          "type": "integer"
        },
        "io_write_bytes": {
          "type": "integer"
        },
        "context_switches": {
          "type": "integer"
        }
      }
    },
    "trace": {
      "type": "object",
      "description": "Full execution trace",
      "properties": {
        "entry_time": {
          "type": "string",
          "format": "date-time"
        },
        "exit_time": {
          "type": "string",
          "format": "date-time"
        },
        "full_stack": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "function": {"type": "string"},
              "file": {"type": "string"},
              "line": {"type": "integer"},
              "locals": {"type": "object"}
            }
          }
        }
      }
    }
  },
  "additionalProperties": true
}
```

**Tier 3 Example Log Entries:**

```json
{
  "timestamp": "2024-01-15T08:23:47.100Z",
  "level": "DEBUG",
  "component": "task_executor",
  "message": "Entering task execution pipeline",
  "correlation_id": "a1b2c3d4e5f67890",
  "context": {
    "request_id": "a1b2c3d4e5f67890",
    "call_depth": 2,
    "function_name": "execute_task",
    "line_number": 156,
    "file_path": "src/core/task_executor.py"
  },
  "payload": {
    "input_params": {
      "task_id": "task_001",
      "task_type": "analysis"
    }
  },
  "performance": {
    "cpu_percent": 12.5,
    "memory_rss_mb": 64.2
  }
}
```

```json
{
  "timestamp": "2024-01-15T08:23:47.145Z",
  "level": "TRACE",
  "component": "llm_client",
  "message": "LLM API response received",
  "correlation_id": "a1b2c3d4e5f67890",
  "context": {
    "parent_correlation_id": "a1b2c3d4e5f67890",
    "call_depth": 4,
    "function_name": "_handle_response",
    "line_number": 89
  },
  "payload": {
    "raw_response": "{\"choices\":[{\"message\":{\"content\":\"Analysis complete...\"}}]}",
    "intermediate_state": {
      "tokens_used": 245,
      "response_time_ms": 1200
    }
  },
  "trace": {
    "entry_time": "2024-01-15T08:23:46.000Z",
    "exit_time": "2024-01-15T08:23:47.145Z"
  }
}
```

---

### 4.1.4 Log Level Definitions

| Level | Numeric | When to Use | Example |
|-------|---------|-------------|---------|
| ERROR | 40 | Unrecoverable failures requiring intervention | "Database connection lost" |
| WARN | 30 | Degraded operation, potential issues | "High memory usage detected" |
| INFO | 20 | Normal operational events | "Task completed successfully" |
| DEBUG | 10 | Detailed diagnostic information | "Entering function X with params Y" |
| TRACE | 5 | Verbose execution tracing | "Variable state: {...}" |

---

### 4.1.5 Correlation ID Tracking

**Generation:**
```python
import secrets

def generate_correlation_id() -> str:
    """Generate 16-character hex correlation ID"""
    return secrets.token_hex(8)  # 16 hex characters
```

**Propagation Rules:**
1. New correlation ID generated at entry points (API calls, scheduled tasks)
2. Same correlation ID propagated through entire call chain
3. Child operations append suffix: `parent_id:child_id`
4. Maximum depth: 5 levels (truncated beyond)

**Context Injection:**
```python
import contextvars

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('correlation_id')
request_context_var: contextvars.ContextVar[dict] = contextvars.ContextVar('request_context')

def get_correlation_id() -> str:
    """Get current correlation ID or generate new"""
    try:
        return correlation_id_var.get()
    except LookupError:
        new_id = generate_correlation_id()
        correlation_id_var.set(new_id)
        return new_id
```

---

## 4.2 The "Panic Button"

### 4.2.1 Overview

The Panic Button provides emergency shutdown capability with state preservation. It is the last-resort mechanism when normal shutdown fails or when immediate termination is required.

**Activation Methods:**
1. Web Dashboard kill switch (authenticated)
2. Direct API call (authenticated)
3. Host filesystem signal file
4. Container orchestrator signal (SIGTERM/SIGKILL)

---

### 4.2.2 Manual Override Procedures

#### EMERGENCY PROCEDURE A: Dashboard Kill Switch

**When to Use:** Normal emergency shutdown via Web GUI

**Steps:**
1. Access Talos Dashboard via Tailscale
2. Navigate to "System" → "Emergency Controls"
3. Click red "PANIC STOP" button
4. Confirm with admin password
5. Wait for shutdown confirmation (max 30 seconds)

**Expected Output:**
```
[2024-01-15T08:30:00Z] INFO: Panic button activated by user: admin
[2024-01-15T08:30:00Z] INFO: Initiating graceful shutdown sequence
[2024-01-15T08:30:02Z] INFO: State saved to /data/emergency_state.json
[2024-01-15T08:30:05Z] INFO: All processes terminated
[2024-01-15T08:30:05Z] INFO: Shutdown complete
```

---

#### EMERGENCY PROCEDURE B: Direct API Call

**When to Use:** Dashboard inaccessible, API still responsive

**Command:**
```bash
# Requires valid session token
curl -X POST https://talos.local:8443/api/v1/emergency/panic \
  -H "Authorization: Bearer ${TALOS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manual emergency stop", "preserve_state": true}' \
  --cacert /path/to/ca.crt
```

**Expected Response:**
```json
{
  "status": "accepted",
  "shutdown_initiated": true,
  "state_preserved": true,
  "estimated_completion": "2024-01-15T08:30:05Z",
  "recovery_token": "recv_abc123xyz789"
}
```

---

#### EMERGENCY PROCEDURE C: Host Filesystem Signal (NO API ACCESS)

**When to Use:** Complete API unresponsiveness

**Command:**
```bash
# Create panic signal file
sudo touch /var/lib/talos/SIGNAL_PANIC

# The watchdog monitors this file every 5 seconds
# System will initiate panic sequence within 5-10 seconds

# Monitor for acknowledgment
sudo tail -f /var/log/talos/orchestrator.log | grep -i panic
```

**File Format (optional metadata):**
```json
{
  "initiated_by": "operator",
  "timestamp": "2024-01-15T08:30:00Z",
  "reason": "API unresponsive",
  "preserve_state": true
}
```

---

#### EMERGENCY PROCEDURE D: Container Orchestrator Kill (NUCLEAR OPTION)

**When to Use:** All other methods failed, system completely frozen

**Docker:**
```bash
# Send SIGTERM first (graceful)
docker kill --signal=SIGTERM talos-orchestrator

# Wait 10 seconds, then SIGKILL if needed
docker kill --signal=SIGKILL talos-orchestrator
```

**Kubernetes:**
```bash
# Delete pod (triggers graceful termination)
kubectl delete pod talos-orchestrator-xxx --grace-period=30

# Force delete (immediate termination)
kubectl delete pod talos-orchestrator-xxx --grace-period=0 --force
```

**Systemd:**
```bash
# Graceful stop
sudo systemctl stop talos

# Force stop
sudo systemctl kill -s SIGKILL talos
```

---

### 4.2.3 Dashboard Kill Switch Implementation

**Frontend Component (React/Vue):**
```typescript
// EmergencyControls.tsx
interface PanicButtonProps {
  onPanic: (reason: string) => Promise<void>;
}

const PanicButton: React.FC<PanicButtonProps> = ({ onPanic }) => {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState('');

  const handlePanic = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }

    try {
      await fetch('/api/v1/emergency/panic', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getAuthToken()}`
        },
        body: JSON.stringify({
          reason: 'Dashboard panic button',
          admin_password: password,
          preserve_state: true
        })
      });
      
      showNotification('Panic sequence initiated', 'warning');
    } catch (error) {
      showNotification('Failed to initiate panic', 'error');
    }
  };

  return (
    <div className="emergency-panel">
      <button 
        className="panic-button"
        onClick={handlePanic}
        disabled={!password && confirming}
      >
        {confirming ? 'CONFIRM PANIC STOP' : 'PANIC STOP'}
      </button>
      {confirming && (
        <input 
          type="password"
          placeholder="Admin password required"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      )}
    </div>
  );
};
```

---

### 4.2.4 Underlying Shell Command Triggered

**panic.sh - Emergency Shutdown Script**

```bash
#!/bin/bash
# panic.sh - Talos Emergency Shutdown Script
# Usage: ./panic.sh [--force] [--no-state] [--reason="..."]
# Classification: OPERATIONAL CRITICAL

set -euo pipefail

# Configuration
TALOS_PID_FILE="/var/run/talos/orchestrator.pid"
TALOS_DATA_DIR="/var/lib/talos"
TALOS_LOG_DIR="/var/log/talos"
STATE_FILE="${TALOS_DATA_DIR}/emergency_state.json"
PANIC_LOG="${TALOS_LOG_DIR}/panic.log"
FORCE=false
PRESERVE_STATE=true
REASON="Manual panic activation"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --no-state)
            PRESERVE_STATE=false
            shift
            ;;
        --reason=*)
            REASON="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging function
log_panic() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date -Iseconds)
    echo "[${timestamp}] ${level}: ${message}" | tee -a "${PANIC_LOG}"
}

# Main panic sequence
main() {
    log_panic "INFO" "=== PANIC SEQUENCE INITIATED ==="
    log_panic "INFO" "Reason: ${REASON}"
    log_panic "INFO" "Force mode: ${FORCE}"
    log_panic "INFO" "Preserve state: ${PRESERVE_STATE}"

    # Step 1: Check if orchestrator is running
    if [[ ! -f "${TALOS_PID_FILE}" ]]; then
        log_panic "WARN" "No PID file found - orchestrator may not be running"
        if [[ "${FORCE}" != "true" ]]; then
            log_panic "ERROR" "Use --force to proceed anyway"
            exit 1
        fi
    fi

    local ORCHESTRATOR_PID
    ORCHESTRATOR_PID=$(cat "${TALOS_PID_FILE}" 2>/dev/null) || true

    if [[ -n "${ORCHESTRATOR_PID}" ]] && kill -0 "${ORCHESTRATOR_PID}" 2>/dev/null; then
        log_panic "INFO" "Orchestrator PID: ${ORCHESTRATOR_PID}"
    else
        log_panic "WARN" "Orchestrator not running"
    fi

    # Step 2: Signal graceful shutdown (if not force)
    if [[ "${FORCE}" != "true" && -n "${ORCHESTRATOR_PID}" ]]; then
        log_panic "INFO" "Sending SIGTERM for graceful shutdown"
        kill -TERM "${ORCHESTRATOR_PID}" 2>/dev/null || true
        
        # Wait for graceful shutdown (max 15 seconds)
        local count=0
        while kill -0 "${ORCHESTRATOR_PID}" 2>/dev/null && [[ $count -lt 15 ]]; do
            sleep 1
            ((count++))
            log_panic "INFO" "Waiting for graceful shutdown... (${count}s)"
        done

        # Force kill if still running
        if kill -0 "${ORCHESTRATOR_PID}" 2>/dev/null; then
            log_panic "WARN" "Graceful shutdown timeout - forcing termination"
            kill -KILL "${ORCHESTRATOR_PID}" 2>/dev/null || true
            sleep 2
        fi
    elif [[ -n "${ORCHESTRATOR_PID}" ]]; then
        log_panic "INFO" "Force mode - sending SIGKILL immediately"
        kill -KILL "${ORCHESTRATOR_PID}" 2>/dev/null || true
        sleep 2
    fi

    # Step 3: Preserve state if requested
    if [[ "${PRESERVE_STATE}" == "true" ]]; then
        log_panic "INFO" "Preserving system state"
        
        # Create state snapshot
        cat > "${STATE_FILE}" << EOF
{
    "panic_timestamp": "$(date -Iseconds)",
    "reason": "${REASON}",
    "pid": "${ORCHESTRATOR_PID:-unknown}",
    "data_dir": "${TALOS_DATA_DIR}",
    "recovery_available": true,
    "force_shutdown": ${FORCE}
}
EOF
        log_panic "INFO" "State preserved to: ${STATE_FILE}"
    fi

    # Step 4: Clean up PID file
    rm -f "${TALOS_PID_FILE}"
    log_panic "INFO" "PID file removed"

    # Step 5: Signal file cleanup
    rm -f "${TALOS_DATA_DIR}/SIGNAL_PANIC"

    log_panic "INFO" "=== PANIC SEQUENCE COMPLETE ==="
    
    # Return recovery instructions
    echo ""
    echo "EMERGENCY SHUTDOWN COMPLETE"
    echo "==========================="
    echo "To restart Talos:"
    echo "  sudo systemctl start talos"
    echo ""
    echo "To recover state:"
    echo "  talos-cli state recover ${STATE_FILE}"
    echo ""
}

# Execute
main "$@"
```

---

### 4.2.5 Graceful Shutdown Sequence

```python
# shutdown_manager.py
import asyncio
import signal
import json
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger('talos.shutdown')

class ShutdownManager:
    """Manages graceful shutdown with state preservation"""
    
    SHUTDOWN_TIMEOUT = 15  # seconds
    STATE_PRESERVE_FILE = '/var/lib/talos/emergency_state.json'
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.shutdown_event = asyncio.Event()
        self.state_preserved = False
        
    async def initiate_graceful_shutdown(self, reason: str, preserve_state: bool = True):
        """Initiate graceful shutdown sequence"""
        logger.info(f"Graceful shutdown initiated: {reason}")
        
        # Phase 1: Stop accepting new work
        logger.info("Phase 1: Stopping new task acceptance")
        self.orchestrator.pause_task_acceptance()
        
        # Phase 2: Wait for active tasks to complete (with timeout)
        logger.info("Phase 2: Waiting for active tasks")
        try:
            await asyncio.wait_for(
                self._wait_for_active_tasks(),
                timeout=self.SHUTDOWN_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for tasks - forcing completion")
            await self._force_task_completion()
        
        # Phase 3: Preserve state if requested
        if preserve_state:
            logger.info("Phase 3: Preserving system state")
            await self._preserve_state(reason)
        
        # Phase 4: Close connections
        logger.info("Phase 4: Closing connections")
        await self._close_connections()
        
        # Phase 5: Signal completion
        logger.info("Phase 5: Shutdown complete")
        self.shutdown_event.set()
        
    async def _wait_for_active_tasks(self):
        """Wait for all active tasks to complete"""
        while self.orchestrator.has_active_tasks():
            logger.debug(f"Waiting for {self.orchestrator.active_task_count()} tasks")
            await asyncio.sleep(0.5)
            
    async def _force_task_completion(self):
        """Force completion of remaining tasks"""
        for task in self.orchestrator.get_active_tasks():
            logger.warning(f"Forcing completion of task: {task.id}")
            task.force_complete()
            
    async def _preserve_state(self, reason: str):
        """Preserve current system state"""
        state = {
            'timestamp': datetime.utcnow().isoformat(),
            'reason': reason,
            'active_tasks': [
                {'id': t.id, 'status': t.status, 'progress': t.progress}
                for t in self.orchestrator.get_active_tasks()
            ],
            'pending_tasks': [
                {'id': t.id, 'priority': t.priority}
                for t in self.orchestrator.get_pending_tasks()
            ],
            'system_state': self.orchestrator.get_system_state(),
            'recovery_available': True
        }
        
        with open(self.STATE_PRESERVE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
            
        self.state_preserved = True
        logger.info(f"State preserved to {self.STATE_PRESERVE_FILE}")
        
    async def _close_connections(self):
        """Close all external connections"""
        await self.orchestrator.close_llm_connections()
        await self.orchestrator.close_database_connections()
        
    def register_signal_handlers(self):
        """Register OS signal handlers"""
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(
                    self._signal_handler(s)
                )
            )
            
    async def _signal_handler(self, sig: signal.Signals):
        """Handle OS signals"""
        logger.info(f"Received signal: {sig.name}")
        await self.initiate_graceful_shutdown(
            reason=f"OS signal: {sig.name}",
            preserve_state=True
        )
```

---

### 4.2.6 Force-Kill Fallback

```python
# force_kill_manager.py
import os
import signal
import psutil
from datetime import datetime, timedelta

class ForceKillManager:
    """Manages force-kill fallback for unresponsive processes"""
    
    FORCE_KILL_TIMEOUT = 20  # seconds after SIGTERM
    
    def __init__(self, pid: int):
        self.pid = pid
        self.sigterm_time: Optional[datetime] = None
        
    def initiate_force_kill_sequence(self):
        """Start force-kill countdown after SIGTERM"""
        self.sigterm_time = datetime.utcnow()
        
        # Schedule force-kill check
        asyncio.create_task(self._force_kill_monitor())
        
    async def _force_kill_monitor(self):
        """Monitor for force-kill condition"""
        while True:
            await asyncio.sleep(1)
            
            if not self._process_exists():
                logger.info("Process terminated gracefully")
                return
                
            elapsed = datetime.utcnow() - self.sigterm_time
            if elapsed > timedelta(seconds=self.FORCE_KILL_TIMEOUT):
                logger.warning("Force-kill timeout reached - sending SIGKILL")
                self._send_sigkill()
                return
                
    def _process_exists(self) -> bool:
        """Check if process still exists"""
        try:
            os.kill(self.pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
            
    def _send_sigkill(self):
        """Send SIGKILL to process"""
        try:
            os.kill(self.pid, signal.SIGKILL)
            logger.info(f"SIGKILL sent to PID {self.pid}")
        except (OSError, ProcessLookupError) as e:
            logger.error(f"Failed to send SIGKILL: {e}")
```

---

### 4.2.7 State Preservation During Emergency Stop

```python
# state_preservation.py
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import zipfile

class StatePreservationManager:
    """Manages state preservation during emergency stops"""
    
    PRESERVE_DIR = Path('/var/lib/talos/emergency_preserves')
    MAX_PRESERVES = 10
    
    def __init__(self):
        self.PRESERVE_DIR.mkdir(parents=True, exist_ok=True)
        
    async def create_emergency_preserve(self, reason: str) -> Path:
        """Create complete state preservation"""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        preserve_name = f"emergency_{timestamp}"
        preserve_path = self.PRESERVE_DIR / preserve_name
        preserve_path.mkdir(parents=True, exist_ok=True)
        
        # Preserve components
        await self._preserve_config(preserve_path)
        await self._preserve_state(preserve_path)
        await self._preserve_logs(preserve_path)
        await self._preserve_task_queue(preserve_path)
        await self._preserve_metadata(preserve_path, reason)
        
        # Create archive
        archive_path = await self._create_archive(preserve_path)
        
        # Cleanup old preserves
        self._cleanup_old_preserves()
        
        return archive_path
        
    async def _preserve_config(self, preserve_path: Path):
        """Preserve configuration files"""
        config_src = Path('/etc/talos/config.yaml')
        config_dst = preserve_path / 'config'
        config_dst.mkdir(exist_ok=True)
        
        if config_src.exists():
            shutil.copy2(config_src, config_dst / 'config.yaml')
            
    async def _preserve_state(self, preserve_path: Path):
        """Preserve runtime state"""
        state_src = Path('/var/lib/talos/state')
        state_dst = preserve_path / 'state'
        
        if state_src.exists():
            shutil.copytree(state_src, state_dst, dirs_exist_ok=True)
            
    async def _preserve_logs(self, preserve_path: Path):
        """Preserve recent logs"""
        logs_src = Path('/var/log/talos')
        logs_dst = preserve_path / 'logs'
        logs_dst.mkdir(exist_ok=True)
        
        # Copy last 24 hours of logs
        for log_file in logs_src.glob('*.log'):
            if self._is_recent(log_file):
                shutil.copy2(log_file, logs_dst)
                
    async def _preserve_task_queue(self, preserve_path: Path):
        """Preserve pending task queue"""
        task_queue = self._get_task_queue()
        
        with open(preserve_path / 'task_queue.json', 'w') as f:
            json.dump(task_queue, f, indent=2)
            
    async def _preserve_metadata(self, preserve_path: Path, reason: str):
        """Preserve metadata about the emergency"""
        metadata = {
            'timestamp': datetime.utcnow().isoformat(),
            'reason': reason,
            'hostname': os.uname().nodename,
            'talos_version': self._get_version(),
            'preserve_version': '1.0'
        }
        
        with open(preserve_path / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
            
    async def _create_archive(self, preserve_path: Path) -> Path:
        """Create compressed archive of preserve"""
        archive_path = Path(f"{preserve_path}.tar.gz")
        
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(preserve_path, arcname=preserve_path.name)
            
        # Remove uncompressed directory
        shutil.rmtree(preserve_path)
        
        return archive_path
        
    def _cleanup_old_preserves(self):
        """Remove oldest preserves if exceeding max"""
        preserves = sorted(self.PRESERVE_DIR.glob('emergency_*.tar.gz'))
        
        while len(preserves) > self.MAX_PRESERVES:
            oldest = preserves.pop(0)
            oldest.unlink()
            logger.info(f"Cleaned up old preserve: {oldest}")
```

---

### 4.2.8 Recovery After Panic Stop

```python
# recovery_manager.py
import json
import tarfile
from pathlib import Path
from typing import Optional, Dict, Any

class RecoveryManager:
    """Manages recovery from panic stop"""
    
    RECOVERY_STATE_FILE = Path('/var/lib/talos/emergency_state.json')
    PRESERVE_DIR = Path('/var/lib/talos/emergency_preserves')
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        
    async def check_recovery_needed(self) -> bool:
        """Check if recovery is needed after startup"""
        if self.RECOVERY_STATE_FILE.exists():
            with open(self.RECOVERY_STATE_FILE) as f:
                state = json.load(f)
            return state.get('recovery_available', False)
        return False
        
    async def perform_recovery(self) -> Dict[str, Any]:
        """Perform recovery from panic state"""
        logger.info("=== RECOVERY SEQUENCE INITIATED ===")
        
        # Load preserved state
        with open(self.RECOVERY_STATE_FILE) as f:
            state = json.load(f)
            
        recovery_report = {
            'success': True,
            'original_timestamp': state['timestamp'],
            'reason': state['reason'],
            'tasks_recovered': 0,
            'tasks_failed': 0,
            'errors': []
        }
        
        # Recover active tasks
        for task_info in state.get('active_tasks', []):
            try:
                await self._recover_task(task_info)
                recovery_report['tasks_recovered'] += 1
            except Exception as e:
                logger.error(f"Failed to recover task {task_info['id']}: {e}")
                recovery_report['tasks_failed'] += 1
                recovery_report['errors'].append(str(e))
                
        # Recover pending tasks
        for task_info in state.get('pending_tasks', []):
            try:
                await self._requeue_task(task_info)
                recovery_report['tasks_recovered'] += 1
            except Exception as e:
                logger.error(f"Failed to requeue task {task_info['id']}: {e}")
                recovery_report['tasks_failed'] += 1
                
        # Clear recovery state
        self.RECOVERY_STATE_FILE.unlink()
        
        logger.info("=== RECOVERY SEQUENCE COMPLETE ===")
        return recovery_report
        
    async def recover_from_archive(self, archive_path: Path) -> Dict[str, Any]:
        """Recover from emergency preserve archive"""
        logger.info(f"Recovering from archive: {archive_path}")
        
        # Extract archive
        extract_path = self.PRESERVE_DIR / 'recovery_temp'
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(extract_path)
            
        # Load metadata
        metadata_path = extract_path / 'metadata.json'
        with open(metadata_path) as f:
            metadata = json.load(f)
            
        # Restore components
        await self._restore_config(extract_path / 'config')
        await self._restore_state(extract_path / 'state')
        await self._restore_task_queue(extract_path / 'task_queue.json')
        
        # Cleanup
        shutil.rmtree(extract_path)
        
        return {
            'success': True,
            'recovered_from': str(archive_path),
            'original_timestamp': metadata['timestamp'],
            'reason': metadata['reason']
        }
```

---

## 4.3 Health Check & Watchdog

### 4.3.1 Health Check Endpoint Specification

**Endpoint:** `GET /health`  
**Port:** 8080 (internal only)  
**Authentication:** None (internal network only)

**Response Format:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2024-01-15T08:30:00Z",
  "version": "4.0.0",
  "checks": {
    "orchestrator": {
      "status": "pass|fail|warn",
      "last_heartbeat": "2024-01-15T08:29:59Z",
      "event_loop_blocked": false,
      "block_duration_ms": 0
    },
    "database": {
      "status": "pass|fail",
      "response_time_ms": 5,
      "connection_pool": {
        "active": 3,
        "idle": 7,
        "max": 20
      }
    },
    "memory": {
      "status": "pass|warn|fail",
      "used_mb": 512,
      "total_mb": 2048,
      "percent": 25
    },
    "disk": {
      "status": "pass|warn|fail",
      "used_gb": 45,
      "total_gb": 100,
      "percent": 45
    }
  },
  "uptime_seconds": 86400
}
```

**Status Codes:**
- `200 OK` - All checks pass (healthy)
- `200 OK` - Some checks warn (degraded)
- `503 Service Unavailable` - Critical check fails (unhealthy)

---

### 4.3.2 Health Check Implementation

```python
# health_check.py
import asyncio
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    
class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

@dataclass
class HealthCheckResult:
    status: CheckStatus
    details: Dict[str, Any]
    
@dataclass  
class HealthReport:
    status: HealthStatus
    timestamp: str
    version: str
    checks: Dict[str, Dict[str, Any]]
    uptime_seconds: int

class HealthChecker:
    """Comprehensive health check system"""
    
    # Thresholds
    MEMORY_WARN_PERCENT = 70
    MEMORY_FAIL_PERCENT = 90
    DISK_WARN_PERCENT = 80
    DISK_FAIL_PERCENT = 95
    DB_RESPONSE_WARN_MS = 100
    DB_RESPONSE_FAIL_MS = 5000
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.start_time = time.time()
        self.last_event_loop_check = time.time()
        self.event_loop_blocked = False
        self.block_start_time: Optional[float] = None
        
    async def run_health_check(self) -> HealthReport:
        """Run all health checks and return report"""
        checks = {}
        
        # Run checks concurrently
        results = await asyncio.gather(
            self._check_orchestrator(),
            self._check_database(),
            self._check_memory(),
            self._check_disk(),
            return_exceptions=True
        )
        
        checks['orchestrator'] = self._format_result(results[0])
        checks['database'] = self._format_result(results[1])
        checks['memory'] = self._format_result(results[2])
        checks['disk'] = self._format_result(results[3])
        
        # Determine overall status
        status = self._determine_overall_status(checks)
        
        return HealthReport(
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            version=self._get_version(),
            checks=checks,
            uptime_seconds=int(time.time() - self.start_time)
        )
        
    async def _check_orchestrator(self) -> HealthCheckResult:
        """Check orchestrator health"""
        heartbeat_age = time.time() - self.orchestrator.last_heartbeat
        
        # Check event loop blocking
        event_loop_ok = not self.event_loop_blocked
        block_duration = 0
        
        if self.event_loop_blocked and self.block_start_time:
            block_duration = time.time() - self.block_start_time
            
        if heartbeat_age > 30:
            status = CheckStatus.FAIL
        elif heartbeat_age > 10:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.PASS
            
        if self.event_loop_blocked:
            status = CheckStatus.FAIL
            
        return HealthCheckResult(
            status=status,
            details={
                'last_heartbeat': self.orchestrator.last_heartbeat,
                'heartbeat_age_seconds': heartbeat_age,
                'event_loop_blocked': self.event_loop_blocked,
                'block_duration_ms': int(block_duration * 1000)
            }
        )
        
    async def _check_database(self) -> HealthCheckResult:
        """Check database connectivity"""
        start = time.time()
        try:
            await self.orchestrator.db.ping()
            response_time = (time.time() - start) * 1000
            
            if response_time > self.DB_RESPONSE_FAIL_MS:
                status = CheckStatus.FAIL
            elif response_time > self.DB_RESPONSE_WARN_MS:
                status = CheckStatus.WARN
            else:
                status = CheckStatus.PASS
                
            pool_stats = self.orchestrator.db.get_pool_stats()
            
            return HealthCheckResult(
                status=status,
                details={
                    'response_time_ms': round(response_time, 2),
                    'connection_pool': pool_stats
                }
            )
        except Exception as e:
            return HealthCheckResult(
                status=CheckStatus.FAIL,
                details={'error': str(e)}
            )
            
    async def _check_memory(self) -> HealthCheckResult:
        """Check memory usage"""
        memory = psutil.virtual_memory()
        
        if memory.percent > self.MEMORY_FAIL_PERCENT:
            status = CheckStatus.FAIL
        elif memory.percent > self.MEMORY_WARN_PERCENT:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.PASS
            
        return HealthCheckResult(
            status=status,
            details={
                'used_mb': memory.used // (1024 * 1024),
                'total_mb': memory.total // (1024 * 1024),
                'percent': memory.percent
            }
        )
        
    async def _check_disk(self) -> HealthCheckResult:
        """Check disk usage"""
        disk = psutil.disk_usage('/var/lib/talos')
        percent = (disk.used / disk.total) * 100
        
        if percent > self.DISK_FAIL_PERCENT:
            status = CheckStatus.FAIL
        elif percent > self.DISK_WARN_PERCENT:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.PASS
            
        return HealthCheckResult(
            status=status,
            details={
                'used_gb': disk.used // (1024 * 1024 * 1024),
                'total_gb': disk.total // (1024 * 1024 * 1024),
                'percent': round(percent, 1)
            }
        )
        
    def _format_result(self, result) -> Dict[str, Any]:
        """Format check result for response"""
        if isinstance(result, Exception):
            return {'status': 'fail', 'error': str(result)}
        return {'status': result.status.value, **result.details}
        
    def _determine_overall_status(self, checks: Dict) -> HealthStatus:
        """Determine overall health status from checks"""
        statuses = [c['status'] for c in checks.values()]
        
        if 'fail' in statuses:
            return HealthStatus.UNHEALTHY
        elif 'warn' in statuses:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY
```

---

### 4.3.3 Watchdog Configuration

```yaml
# watchdog.yaml
watchdog:
  enabled: true
  check_interval_seconds: 5
  
  # Event loop monitoring
  event_loop:
    enabled: true
    max_block_seconds: 30
    heartbeat_interval_seconds: 1
    
  # Process monitoring
  process:
    enabled: true
    max_memory_percent: 90
    max_cpu_percent: 95
    
  # Container restart
  restart:
    enabled: true
    max_restarts_per_hour: 5
    backoff_seconds: 10
    
  # Alerting
  alerts:
    enabled: true
    webhook_url: "${WATCHDOG_WEBHOOK_URL}"
    on_event_loop_block: true
    on_memory_critical: true
    on_restart: true
```

---

### 4.3.4 30-Second Event Loop Block Detection

```python
# event_loop_watchdog.py
import asyncio
import time
import signal
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger('talos.watchdog')

class EventLoopWatchdog:
    """Detects event loop blocking with 30-second threshold"""
    
    BLOCK_THRESHOLD_SECONDS = 30
    HEARTBEAT_INTERVAL = 1.0
    
    def __init__(self, on_block_detected: callable):
        self.on_block_detected = on_block_detected
        self.last_heartbeat = time.time()
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the watchdog"""
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Event loop watchdog started")
        
    async def stop(self):
        """Stop the watchdog"""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        logger.info("Event loop watchdog stopped")
        
    async def _heartbeat_loop(self):
        """Send regular heartbeats"""
        while self.running:
            self.last_heartbeat = time.time()
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            
    async def _monitor_loop(self):
        """Monitor for event loop blocking"""
        while self.running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            
            block_duration = time.time() - self.last_heartbeat
            
            if block_duration > self.BLOCK_THRESHOLD_SECONDS:
                logger.critical(
                    f"EVENT LOOP BLOCKED for {block_duration:.1f}s - "
                    f"exceeds threshold of {self.BLOCK_THRESHOLD_SECONDS}s"
                )
                
                # Trigger callback
                await self.on_block_detected(block_duration)
                
                # Stop monitoring to prevent repeated triggers
                self.running = False
                break
            elif block_duration > 5:
                logger.warning(f"Event loop delay detected: {block_duration:.1f}s")
                
class BlockRecoveryHandler:
    """Handles recovery from event loop block"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.recovery_attempted = False
        
    async def handle_block(self, block_duration: float):
        """Handle detected event loop block"""
        if self.recovery_attempted:
            logger.error("Recovery already attempted - preventing loop")
            return
            
        self.recovery_attempted = True
        
        # Log critical event
        await self._log_block_event(block_duration)
        
        # Preserve state
        await self._preserve_state()
        
        # Trigger container restart
        await self._trigger_restart()
        
    async def _log_block_event(self, block_duration: float):
        """Log the block event for post-mortem analysis"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'event_loop_blocked',
            'block_duration_seconds': block_duration,
            'threshold_seconds': EventLoopWatchdog.BLOCK_THRESHOLD_SECONDS,
            'active_tasks': self.orchestrator.get_active_task_info(),
            'memory_usage': self._get_memory_info(),
            'thread_dump': self._get_thread_dump()
        }
        
        # Write to dedicated block log
        with open('/var/log/talos/block_events.log', 'a') as f:
            f.write(json.dumps(event) + '\n')
            
    async def _preserve_state(self):
        """Preserve state before restart"""
        preservation_manager = StatePreservationManager()
        await preservation_manager.create_emergency_preserve(
            reason=f"Event loop blocked for {block_duration}s"
        )
        
    async def _trigger_restart(self):
        """Trigger container restart"""
        logger.critical("Triggering container restart")
        
        # Option 1: Exit with error code (container orchestrator will restart)
        # os._exit(1)
        
        # Option 2: Signal tini to restart
        os.kill(1, signal.SIGTERM)
```

---

### 4.3.5 Container Restart Procedure

```dockerfile
# Dockerfile - Restart configuration
FROM python:3.11-slim

# Install tini for proper signal handling and zombie reaping
RUN apt-get update && apt-get install -y tini

# Configure restart policy via docker-compose or orchestrator
# restart: unless-stopped
# restart_policy:
#   condition: on-failure
#   delay: 10s
#   max_attempts: 5
#   window: 60s

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "talos.orchestrator"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  talos-orchestrator:
    build: .
    restart: unless-stopped
    deploy:
      restart_policy:
        condition: on-failure
        delay: 10s
        max_attempts: 5
        window: 60s
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
    labels:
      - "com.talos.watchdog.enabled=true"
      - "com.talos.watchdog.max_restarts=5"
```

---

### 4.3.6 State Recovery After Restart

```python
# restart_recovery.py
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger('talos.restart_recovery')

class RestartRecoveryManager:
    """Manages state recovery after container restart"""
    
    STATE_DIR = Path('/var/lib/talos')
    RECOVERY_MARKER = STATE_DIR / '.recovery_in_progress'
    STATE_FILE = STATE_DIR / 'orchestrator_state.json'
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        
    async def check_and_recover(self) -> bool:
        """Check if recovery needed and perform it"""
        
        # Check for recovery marker (indicates unclean shutdown)
        if self.RECOVERY_MARKER.exists():
            logger.warning("Recovery marker found - unclean shutdown detected")
            
            # Load previous state
            if self.STATE_FILE.exists():
                with open(self.STATE_FILE) as f:
                    state = json.load(f)
                    
                logger.info(f"Recovering from state: {state['timestamp']}")
                
                # Perform recovery
                await self._recover_state(state)
                
                # Clear marker
                self.RECOVERY_MARKER.unlink()
                
                return True
            else:
                logger.error("Recovery marker present but no state file found")
                self.RECOVERY_MARKER.unlink()
                
        return False
        
    async def _recover_state(self, state: Dict[str, Any]):
        """Recover orchestrator state"""
        
        # Restore task queue
        for task_data in state.get('pending_tasks', []):
            await self._restore_task(task_data)
            
        # Restore configuration
        if 'config' in state:
            self.orchestrator.apply_config(state['config'])
            
        # Log recovery completion
        logger.info("State recovery complete")
        
    async def pre_shutdown_save(self):
        """Save state before shutdown"""
        state = {
            'timestamp': datetime.utcnow().isoformat(),
            'pending_tasks': [
                task.to_dict() for task in self.orchestrator.get_pending_tasks()
            ],
            'config': self.orchestrator.get_config(),
            'version': self.orchestrator.version
        }
        
        # Create recovery marker
        self.RECOVERY_MARKER.touch()
        
        # Save state
        with open(self.STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
            
        logger.info("State saved for potential recovery")
```

---

## 4.4 Backup & Restore

### 4.4.1 Backup Contents Specification

**Full Backup Includes:**

| Component | Path | Description |
|-----------|------|-------------|
| Configuration | `/etc/talos/` | All config files including secrets |
| State Data | `/var/lib/talos/state/` | Runtime state, task history |
| Database | `/var/lib/talos/db/` | SQLite database files |
| Audit Logs | `/var/log/talos/audit/` | Tier 1 logs (indefinite retention) |
| Custom Code | `/opt/talos/custom/` | User extensions and plugins |
| SSL Certificates | `/etc/talos/ssl/` | TLS certificates |

**Backup Exclusions:**
- Tier 2/3 logs (rotated, 50MB max)
- Temporary files
- Cache directories
- Process PID files

---

### 4.4.2 backup.tar.gz Structure

```
backup.tar.gz
├── metadata.json           # Backup metadata
├── manifest.json           # File manifest with checksums
├── config/
│   ├── config.yaml         # Main configuration
│   ├── config.yaml.backup  # Previous config backup
│   └── secrets/            # Encrypted secrets (if enabled)
├── state/
│   ├── orchestrator.json   # Orchestrator state
│   ├── task_queue.json     # Pending tasks
│   └── sessions/           # Active session data
├── database/
│   ├── talos.db            # Main database
│   └── talos.db-wal        # Write-ahead log
├── logs/
│   └── audit/              # Tier 1 audit logs only
├── custom/
│   ├── plugins/            # Custom plugins
│   └── extensions/         # User extensions
└── ssl/
    ├── cert.pem            # TLS certificate
    ├── key.pem             # TLS private key
    └── ca.pem              # CA certificate (if custom)
```

**metadata.json:**
```json
{
  "backup_version": "4.0",
  "created_at": "2024-01-15T08:30:00Z",
  "created_by": "backup_service",
  "hostname": "talos-prod-01",
  "talos_version": "4.0.0",
  "backup_type": "full",
  "compressed": true,
  "encryption": null,
  "checksum_algorithm": "sha256"
}
```

---

### 4.4.3 restore.sh - Complete Shell Script

```bash
#!/bin/bash
################################################################################
# restore.sh - Talos Disaster Recovery Script
# Version: 4.0
# Classification: OPERATIONAL CRITICAL
#
# Usage:
#   ./restore.sh <backup_file> [options]
#
# Options:
#   --dry-run          Validate backup without restoring
#   --force            Skip confirmation prompts
#   --target-dir=DIR   Restore to different directory
#   --partial=TYPE     Partial restore (config|state|database|logs)
#   --verify-only      Only verify backup integrity
#   --new-host         New machine restoration mode
#
# Examples:
#   ./restore.sh backup_20240115.tar.gz
#   ./restore.sh backup.tar.gz --dry-run
#   ./restore.sh backup.tar.gz --partial=config
#   ./restore.sh backup.tar.gz --new-host
################################################################################

set -euo pipefail

#==============================================================================
# CONFIGURATION
#==============================================================================

readonly SCRIPT_VERSION="4.0"
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_FILE="/var/log/talos/restore.log"
readonly LOCK_FILE="/var/run/talos_restore.lock"

# Default paths
TALOS_CONFIG_DIR="/etc/talos"
TALOS_DATA_DIR="/var/lib/talos"
TALOS_LOG_DIR="/var/log/talos"
TALOS_CUSTOM_DIR="/opt/talos/custom"
TALOS_SSL_DIR="/etc/talos/ssl"

# Colors for output (disable if not terminal)
if [[ -t 1 ]]; then
    readonly RED='\033[0;31m'
    readonly GREEN='\033[0;32m'
    readonly YELLOW='\033[1;33m'
    readonly BLUE='\033[0;34m'
    readonly NC='\033[0m' # No Color
else
    readonly RED=''
    readonly GREEN=''
    readonly YELLOW=''
    readonly BLUE=''
    readonly NC=''
fi

#==============================================================================
# GLOBALS
#==============================================================================

BACKUP_FILE=""
DRY_RUN=false
FORCE=false
VERIFY_ONLY=false
NEW_HOST=false
PARTIAL_RESTORE=""
TARGET_DIR=""
BACKUP_TEMP_DIR=""
RESTORED_ITEMS=()
ERRORS=()

#==============================================================================
# LOGGING FUNCTIONS
#==============================================================================

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Console output
    case "$level" in
        ERROR)   echo -e "${RED}[ERROR]${NC} $message" ;;
        WARN)    echo -e "${YELLOW}[WARN]${NC} $message" ;;
        SUCCESS) echo -e "${GREEN}[SUCCESS]${NC} $message" ;;
        INFO)    echo -e "${BLUE}[INFO]${NC} $message" ;;
        *)       echo "[$level] $message" ;;
    esac
    
    # File logging
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

log_section() {
    echo ""
    log "INFO" "========================================"
    log "INFO" "$1"
    log "INFO" "========================================"
}

#==============================================================================
# UTILITY FUNCTIONS
#==============================================================================

show_usage() {
    cat << EOF
Talos Restore Script v${SCRIPT_VERSION}

Usage: ${SCRIPT_NAME} <backup_file> [options]

Options:
    --dry-run          Validate backup without restoring
    --force            Skip confirmation prompts
    --target-dir=DIR   Restore to different directory
    --partial=TYPE     Partial restore (config|state|database|logs|custom|ssl)
    --verify-only      Only verify backup integrity
    --new-host         New machine restoration mode
    -h, --help         Show this help message

Examples:
    # Full restore
    ${SCRIPT_NAME} backup_20240115.tar.gz

    # Validate backup first
    ${SCRIPT_NAME} backup.tar.gz --dry-run

    # Restore only configuration
    ${SCRIPT_NAME} backup.tar.gz --partial=config

    # Restore to new machine
    ${SCRIPT_NAME} backup.tar.gz --new-host

    # Verify backup integrity
    ${SCRIPT_NAME} backup.tar.gz --verify-only
EOF
}

error_exit() {
    log "ERROR" "$1"
    cleanup
    exit 1
}

cleanup() {
    if [[ -n "$BACKUP_TEMP_DIR" && -d "$BACKUP_TEMP_DIR" ]]; then
        log "INFO" "Cleaning up temporary directory: $BACKUP_TEMP_DIR"
        rm -rf "$BACKUP_TEMP_DIR"
    fi
    
    if [[ -f "$LOCK_FILE" ]]; then
        rm -f "$LOCK_FILE"
    fi
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error_exit "This script must be run as root"
    fi
}

acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid=$(cat "$LOCK_FILE" 2>/dev/null) || true
        if kill -0 "$pid" 2>/dev/null; then
            error_exit "Another restore process is running (PID: $pid)"
        fi
        log "WARN" "Removing stale lock file"
        rm -f "$LOCK_FILE"
    fi
    
    echo $$ > "$LOCK_FILE"
}

#==============================================================================
# BACKUP VALIDATION FUNCTIONS
#==============================================================================

verify_backup_file() {
    local file="$1"
    
    log "INFO" "Verifying backup file: $file"
    
    # Check file exists
    if [[ ! -f "$file" ]]; then
        error_exit "Backup file not found: $file"
    fi
    
    # Check file is readable
    if [[ ! -r "$file" ]]; then
        error_exit "Backup file is not readable: $file"
    fi
    
    # Check file size
    local size
    size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    if [[ "$size" -lt 100 ]]; then
        error_exit "Backup file is too small (${size} bytes)"
    fi
    
    # Verify tar.gz integrity
    if ! tar -tzf "$file" > /dev/null 2>&1; then
        error_exit "Backup file is corrupted or not a valid tar.gz archive"
    fi
    
    log "SUCCESS" "Backup file integrity verified"
}

extract_backup() {
    local file="$1"
    local dest="$2"
    
    log "INFO" "Extracting backup to temporary directory..."
    
    mkdir -p "$dest"
    
    if ! tar -xzf "$file" -C "$dest"; then
        error_exit "Failed to extract backup archive"
    fi
    
    log "SUCCESS" "Backup extracted successfully"
}

verify_manifest() {
    local backup_dir="$1"
    
    log "INFO" "Verifying backup manifest..."
    
    local manifest="$backup_dir/manifest.json"
    local metadata="$backup_dir/metadata.json"
    
    if [[ ! -f "$manifest" ]]; then
        error_exit "Manifest file not found in backup"
    fi
    
    if [[ ! -f "$metadata" ]]; then
        error_exit "Metadata file not found in backup"
    fi
    
    # Verify checksums if available
    if command -v sha256sum > /dev/null 2>&1; then
        while IFS= read -r line; do
            local expected_hash file_path
            expected_hash=$(echo "$line" | cut -d' ' -f1)
            file_path=$(echo "$line" | cut -d' ' -f2)
            
            if [[ -f "$backup_dir/$file_path" ]]; then
                local actual_hash
                actual_hash=$(sha256sum "$backup_dir/$file_path" | cut -d' ' -f1)
                if [[ "$expected_hash" != "$actual_hash" ]]; then
                    error_exit "Checksum mismatch for $file_path"
                fi
            fi
        done < <(jq -r '.files[] | "\(.checksum) \(.path)"' "$manifest" 2>/dev/null || true)
    fi
    
    log "SUCCESS" "Manifest verification complete"
}

#==============================================================================
# RESTORE FUNCTIONS
#==============================================================================

restore_config() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_CONFIG_DIR}"
    
    log_section "RESTORING CONFIGURATION"
    
    local src="$backup_dir/config"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No config directory in backup"
        return 1
    fi
    
    # Create backup of current config
    if [[ -d "$target" && "$DRY_RUN" == false ]]; then
        local config_backup="${target}.backup.$(date +%Y%m%d_%H%M%S)"
        log "INFO" "Backing up current config to: $config_backup"
        cp -r "$target" "$config_backup"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore config to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        chmod 600 "$target"/*.yaml 2>/dev/null || true
        chmod 700 "$target/secrets" 2>/dev/null || true
        RESTORED_ITEMS+=("config")
        log "SUCCESS" "Configuration restored to: $target"
    fi
}

restore_state() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_DATA_DIR}/state"
    
    log_section "RESTORING STATE"
    
    local src="$backup_dir/state"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No state directory in backup"
        return 1
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore state to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        RESTORED_ITEMS+=("state")
        log "SUCCESS" "State restored to: $target"
    fi
}

restore_database() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_DATA_DIR}/db"
    
    log_section "RESTORING DATABASE"
    
    local src="$backup_dir/database"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No database directory in backup"
        return 1
    fi
    
    # Stop Talos if running
    if systemctl is-active --quiet talos 2>/dev/null; then
        if [[ "$DRY_RUN" == false ]]; then
            log "INFO" "Stopping Talos service..."
            systemctl stop talos || true
        fi
    fi
    
    # Backup current database
    if [[ -d "$target" && "$DRY_RUN" == false ]]; then
        local db_backup="${target}.backup.$(date +%Y%m%d_%H%M%S)"
        log "INFO" "Backing up current database to: $db_backup"
        cp -r "$target" "$db_backup"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore database to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        chmod 600 "$target"/*.db 2>/dev/null || true
        RESTORED_ITEMS+=("database")
        log "SUCCESS" "Database restored to: $target"
    fi
}

restore_logs() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_LOG_DIR}/audit"
    
    log_section "RESTORING AUDIT LOGS"
    
    local src="$backup_dir/logs/audit"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No audit logs in backup"
        return 1
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore audit logs to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        chmod 640 "$target"/*.log 2>/dev/null || true
        RESTORED_ITEMS+=("logs")
        log "SUCCESS" "Audit logs restored to: $target"
    fi
}

restore_custom() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_CUSTOM_DIR}"
    
    log_section "RESTORING CUSTOM CODE"
    
    local src="$backup_dir/custom"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No custom code in backup"
        return 1
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore custom code to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        RESTORED_ITEMS+=("custom")
        log "SUCCESS" "Custom code restored to: $target"
    fi
}

restore_ssl() {
    local backup_dir="$1"
    local target="${TARGET_DIR:-$TALOS_SSL_DIR}"
    
    log_section "RESTORING SSL CERTIFICATES"
    
    local src="$backup_dir/ssl"
    
    if [[ ! -d "$src" ]]; then
        log "WARN" "No SSL certificates in backup"
        return 1
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] Would restore SSL certificates to: $target"
    else
        mkdir -p "$target"
        cp -r "$src"/* "$target/"
        chmod 600 "$target"/*.key 2>/dev/null || true
        chmod 644 "$target"/*.pem 2>/dev/null || true
        RESTORED_ITEMS+=("ssl")
        log "SUCCESS" "SSL certificates restored to: $target"
    fi
}

#==============================================================================
# NEW MACHINE RESTORATION
#==============================================================================

new_machine_setup() {
    log_section "NEW MACHINE SETUP"
    
    log "INFO" "Performing new machine restoration..."
    
    # Create required directories
    local dirs=(
        "$TALOS_CONFIG_DIR"
        "$TALOS_DATA_DIR"
        "$TALOS_DATA_DIR/state"
        "$TALOS_DATA_DIR/db"
        "$TALOS_LOG_DIR"
        "$TALOS_LOG_DIR/audit"
        "$TALOS_CUSTOM_DIR"
        "$TALOS_SSL_DIR"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ "$DRY_RUN" == false ]]; then
            mkdir -p "$dir"
            log "INFO" "Created directory: $dir"
        else
            log "INFO" "[DRY-RUN] Would create directory: $dir"
        fi
    done
    
    # Create talos user if doesn't exist
    if ! id -u talos > /dev/null 2>&1; then
        if [[ "$DRY_RUN" == false ]]; then
            log "INFO" "Creating talos user..."
            useradd -r -s /bin/false -d "$TALOS_DATA_DIR" talos
        else
            log "INFO" "[DRY-RUN] Would create talos user"
        fi
    fi
    
    # Set permissions
    if [[ "$DRY_RUN" == false ]]; then
        chown -R talos:talos "$TALOS_DATA_DIR"
        chown -R talos:talos "$TALOS_LOG_DIR"
        chown -R talos:talos "$TALOS_CUSTOM_DIR"
        chmod 750 "$TALOS_CONFIG_DIR"
        chmod 700 "$TALOS_DATA_DIR"
    fi
    
    log "SUCCESS" "New machine setup complete"
}

#==============================================================================
# POST-RESTORE VALIDATION
#==============================================================================

validate_restore() {
    log_section "VALIDATING RESTORE"
    
    local errors=0
    
    # Check config
    if [[ -f "$TALOS_CONFIG_DIR/config.yaml" ]]; then
        log "SUCCESS" "Configuration file exists"
        
        # Validate YAML syntax
        if command -v python3 > /dev/null 2>&1; then
            if python3 -c "import yaml; yaml.safe_load(open('$TALOS_CONFIG_DIR/config.yaml'))" 2>/dev/null; then
                log "SUCCESS" "Configuration YAML is valid"
            else
                log "ERROR" "Configuration YAML is invalid"
                ((errors++))
            fi
        fi
    else
        log "ERROR" "Configuration file not found"
        ((errors++))
    fi
    
    # Check database
    if [[ -f "$TALOS_DATA_DIR/db/talos.db" ]]; then
        log "SUCCESS" "Database file exists"
        
        # Verify SQLite integrity
        if command -v sqlite3 > /dev/null 2>&1; then
            if sqlite3 "$TALOS_DATA_DIR/db/talos.db" "PRAGMA integrity_check;" | grep -q "ok"; then
                log "SUCCESS" "Database integrity verified"
            else
                log "ERROR" "Database integrity check failed"
                ((errors++))
            fi
        fi
    fi
    
    # Check permissions
    if [[ "$(stat -c %U "$TALOS_DATA_DIR" 2>/dev/null)" == "talos" ]]; then
        log "SUCCESS" "Data directory ownership correct"
    else
        log "WARN" "Data directory ownership may be incorrect"
    fi
    
    if [[ $errors -eq 0 ]]; then
        log "SUCCESS" "All validation checks passed"
        return 0
    else
        log "ERROR" "Validation failed with $errors error(s)"
        return 1
    fi
}

#==============================================================================
# MAIN
#==============================================================================

main() {
    # Parse arguments
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi
    
    BACKUP_FILE="$1"
    shift
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --verify-only)
                VERIFY_ONLY=true
                shift
                ;;
            --new-host)
                NEW_HOST=true
                shift
                ;;
            --target-dir=*)
                TARGET_DIR="${1#*=}"
                shift
                ;;
            --partial=*)
                PARTIAL_RESTORE="${1#*=}"
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1"
                ;;
        esac
    done
    
    # Setup logging
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    
    log_section "TALOS RESTORE v${SCRIPT_VERSION}"
    log "INFO" "Backup file: $BACKUP_FILE"
    log "INFO" "Dry run: $DRY_RUN"
    log "INFO" "New host: $NEW_HOST"
    log "INFO" "Partial restore: ${PARTIAL_RESTORE:-none}"
    
    # Pre-flight checks
    check_root
    acquire_lock
    
    # Verify backup
    verify_backup_file "$BACKUP_FILE"
    
    # Create temp directory
    BACKUP_TEMP_DIR=$(mktemp -d)
    log "INFO" "Using temporary directory: $BACKUP_TEMP_DIR"
    
    # Extract backup
    extract_backup "$BACKUP_FILE" "$BACKUP_TEMP_DIR"
    
    # Verify manifest
    verify_manifest "$BACKUP_TEMP_DIR"
    
    # Exit if verify-only
    if [[ "$VERIFY_ONLY" == true ]]; then
        log "SUCCESS" "Backup verification complete"
        cleanup
        exit 0
    fi
    
    # Confirmation (unless force)
    if [[ "$FORCE" == false && "$DRY_RUN" == false ]]; then
        echo ""
        echo -e "${YELLOW}WARNING: This will overwrite existing Talos data!${NC}"
        read -p "Are you sure you want to continue? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log "INFO" "Restore cancelled by user"
            cleanup
            exit 0
        fi
    fi
    
    # New machine setup
    if [[ "$NEW_HOST" == true ]]; then
        new_machine_setup
    fi
    
    # Perform restore
    if [[ -n "$PARTIAL_RESTORE" ]]; then
        case "$PARTIAL_RESTORE" in
            config)   restore_config "$BACKUP_TEMP_DIR" ;;
            state)    restore_state "$BACKUP_TEMP_DIR" ;;
            database) restore_database "$BACKUP_TEMP_DIR" ;;
            logs)     restore_logs "$BACKUP_TEMP_DIR" ;;
            custom)   restore_custom "$BACKUP_TEMP_DIR" ;;
            ssl)      restore_ssl "$BACKUP_TEMP_DIR" ;;
            *)        error_exit "Unknown partial restore type: $PARTIAL_RESTORE" ;;
        esac
    else
        # Full restore
        restore_config "$BACKUP_TEMP_DIR"
        restore_state "$BACKUP_TEMP_DIR"
        restore_database "$BACKUP_TEMP_DIR"
        restore_logs "$BACKUP_TEMP_DIR"
        restore_custom "$BACKUP_TEMP_DIR"
        restore_ssl "$BACKUP_TEMP_DIR"
    fi
    
    # Validate restore
    if [[ "$DRY_RUN" == false ]]; then
        validate_restore
    fi
    
    # Summary
    log_section "RESTORE SUMMARY"
    
    if [[ ${#RESTORED_ITEMS[@]} -gt 0 ]]; then
        log "SUCCESS" "Restored components:"
        for item in "${RESTORED_ITEMS[@]}"; do
            log "INFO" "  - $item"
        done
    fi
    
    if [[ ${#ERRORS[@]} -gt 0 ]]; then
        log "ERROR" "Errors encountered:"
        for err in "${ERRORS[@]}"; do
            log "ERROR" "  - $err"
        done
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log "INFO" "[DRY-RUN] No changes were made"
    else
        log "SUCCESS" "Restore completed successfully"
        log "INFO" "You may now start Talos: sudo systemctl start talos"
    fi
    
    cleanup
    exit 0
}

# Run main
trap cleanup EXIT INT TERM
main "$@"
```

---

### 4.4.4 New Machine Restoration Procedure

**Prerequisites:**
```bash
# 1. Install dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-pip sqlite3 jq tar gzip

# 2. Create talos user
sudo useradd -r -s /bin/false -d /var/lib/talos talos

# 3. Download restore script
curl -o /usr/local/bin/talos-restore \
  https://releases.talos.io/v4.0/restore.sh
sudo chmod +x /usr/local/bin/talos-restore
```

**Restoration Steps:**
```bash
# 1. Copy backup to new machine
scp backup_20240115.tar.gz newhost:/tmp/

# 2. Run new host restoration
sudo talos-restore /tmp/backup_20240115.tar.gz --new-host

# 3. Verify restoration
sudo talos-restore /tmp/backup_20240115.tar.gz --verify-only

# 4. Start Talos
sudo systemctl start talos
sudo systemctl enable talos

# 5. Verify service
sudo systemctl status talos
curl -f http://localhost:8080/health
```

---

### 4.4.5 Data Validation After Restore

```python
# validate_restore.py
import sqlite3
import yaml
import json
from pathlib import Path
from typing import List, Dict, Any

class RestoreValidator:
    """Validates restored Talos installation"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        
    def validate_all(self) -> Dict[str, Any]:
        """Run all validation checks"""
        self.validate_config()
        self.validate_database()
        self.validate_permissions()
        self.validate_ssl()
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings
        }
        
    def validate_config(self):
        """Validate configuration files"""
        config_path = Path('/etc/talos/config.yaml')
        
        if not config_path.exists():
            self.errors.append("Configuration file not found")
            return
            
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
                
            # Check required fields
            required = ['version', 'orchestrator', 'logging']
            for field in required:
                if field not in config:
                    self.errors.append(f"Missing required config field: {field}")
                    
        except yaml.YAMLError as e:
            self.errors.append(f"Invalid YAML syntax: {e}")
            
    def validate_database(self):
        """Validate database integrity"""
        db_path = Path('/var/lib/talos/db/talos.db')
        
        if not db_path.exists():
            self.errors.append("Database file not found")
            return
            
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Run integrity check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            if result[0] != 'ok':
                self.errors.append(f"Database integrity check failed: {result[0]}")
                
            # Check required tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            required_tables = ['tasks', 'sessions', 'audit_log']
            for table in required_tables:
                if table not in tables:
                    self.errors.append(f"Missing required table: {table}")
                    
            conn.close()
            
        except sqlite3.Error as e:
            self.errors.append(f"Database error: {e}")
            
    def validate_permissions(self):
        """Validate file permissions"""
        paths = [
            ('/var/lib/talos', 0o700),
            ('/etc/talos/config.yaml', 0o600),
            ('/var/lib/talos/db/talos.db', 0o600)
        ]
        
        for path, expected_mode in paths:
            p = Path(path)
            if p.exists():
                actual_mode = p.stat().st_mode & 0o777
                if actual_mode != expected_mode:
                    self.warnings.append(
                        f"Permission mismatch for {path}: "
                        f"expected {oct(expected_mode)}, got {oct(actual_mode)}"
                    )
```

---

### 4.4.6 Partial Restore Options

| Restore Type | Command | Use Case |
|--------------|---------|----------|
| Configuration Only | `--partial=config` | Migrate settings, keep data |
| Database Only | `--partial=database` | Restore corrupted database |
| State Only | `--partial=state` | Restore task queue |
| Logs Only | `--partial=logs` | Audit trail recovery |
| Custom Code | `--partial=custom` | Plugin/extension recovery |
| SSL Certs | `--partial=ssl` | Certificate rotation |

---

## 4.5 Operational Monitoring

### 4.5.1 Key Metrics to Monitor

**System Metrics:**

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| CPU Usage | psutil | >80% warn, >95% critical |
| Memory Usage | psutil | >70% warn, >90% critical |
| Disk Usage | psutil | >80% warn, >95% critical |
| Load Average | os.loadavg | >2.0 warn, >4.0 critical |
| Open File Descriptors | /proc/self/fd | >80% of limit warn |

**Application Metrics:**

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Event Loop Lag | Custom | >100ms warn, >500ms critical |
| Active Tasks | Orchestrator | >100 warn |
| Task Queue Depth | Orchestrator | >50 warn, >100 critical |
| API Response Time | Middleware | >500ms warn, >2000ms critical |
| Error Rate | Logging | >1% warn, >5% critical |
| Database Connections | Pool | >80% of max warn |

**Business Metrics:**

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Tasks Completed/Hour | Orchestrator | <baseline - 20% warn |
| Failed Task Rate | Orchestrator | >5% warn, >10% critical |
| LLM API Latency | Client | >5s warn, >10s critical |
| LLM API Errors | Client | >10% warn |

---

### 4.5.2 Alert Thresholds

```yaml
# alerts.yaml
alerts:
  channels:
    webhook:
      url: "${ALERT_WEBHOOK_URL}"
      timeout_seconds: 10
    email:
      smtp_host: "${SMTP_HOST}"
      smtp_port: 587
      from: "talos-alerts@example.com"
      to: "ops@example.com"
      
  rules:
    # System alerts
    - name: "high_cpu"
      condition: "cpu_percent > 80"
      severity: "warning"
      cooldown_minutes: 5
      message: "High CPU usage: {{value}}%"
      
    - name: "critical_cpu"
      condition: "cpu_percent > 95"
      severity: "critical"
      cooldown_minutes: 1
      message: "CRITICAL: CPU usage {{value}}%"
      channels: [webhook, email]
      
    - name: "high_memory"
      condition: "memory_percent > 70"
      severity: "warning"
      cooldown_minutes: 5
      message: "High memory usage: {{value}}%"
      
    - name: "critical_memory"
      condition: "memory_percent > 90"
      severity: "critical"
      cooldown_minutes: 1
      message: "CRITICAL: Memory usage {{value}}%"
      channels: [webhook, email]
      
    - name: "disk_full"
      condition: "disk_percent > 95"
      severity: "critical"
      cooldown_minutes: 10
      message: "CRITICAL: Disk nearly full: {{value}}%"
      channels: [webhook, email]
      
    # Application alerts
    - name: "event_loop_lag"
      condition: "event_loop_lag_ms > 500"
      severity: "critical"
      cooldown_minutes: 1
      message: "Event loop blocked: {{value}}ms"
      channels: [webhook, email]
      
    - name: "high_error_rate"
      condition: "error_rate_5m > 0.05"
      severity: "warning"
      cooldown_minutes: 5
      message: "High error rate: {{value}}%"
      
    - name: "task_queue_full"
      condition: "task_queue_depth > 100"
      severity: "warning"
      cooldown_minutes: 5
      message: "Task queue depth: {{value}}"
      
    - name: "llm_api_down"
      condition: "llm_api_healthy == false"
      severity: "critical"
      cooldown_minutes: 1
      message: "LLM API unavailable"
      channels: [webhook, email]
```

---

### 4.5.3 Dashboard Indicators

**Health Status Widget:**
```javascript
// Dashboard health indicator component
const HealthIndicator = ({ status, metrics }) => {
  const getStatusColor = (status) => {
    switch(status) {
      case 'healthy': return 'green';
      case 'degraded': return 'yellow';
      case 'unhealthy': return 'red';
      default: return 'gray';
    }
  };
  
  return (
    <div className={`health-indicator ${getStatusColor(status)}`}>
      <div className="status-badge">{status.toUpperCase()}</div>
      <div className="metrics">
        <div>CPU: {metrics.cpu}%</div>
        <div>Memory: {metrics.memory}%</div>
        <div>Tasks: {metrics.activeTasks}</div>
        <div>Uptime: {formatUptime(metrics.uptime)}</div>
      </div>
    </div>
  );
};
```

**Key Indicators Panel:**

| Indicator | Normal | Warning | Critical |
|-----------|--------|---------|----------|
| System Status | Green | Yellow | Red |
| Event Loop | <100ms | 100-500ms | >500ms |
| Task Queue | <50 | 50-100 | >100 |
| Error Rate | <1% | 1-5% | >5% |
| DB Connections | <80% | 80-95% | >95% |

---

### 4.5.4 Log Analysis Queries

**Using jq for JSON log analysis:**

```bash
# Find all ERROR logs from last hour
jq 'select(.level == "ERROR" and .timestamp >= "'$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M)'")' /var/log/talos/orchestrator.log

# Count errors by component
jq -s 'group_by(.component) | map({component: .[0].component, count: length})' /var/log/talos/orchestrator.log

# Find slow operations (>1s)
jq 'select(.metadata.duration_ms > 1000) | {timestamp, component, message, duration: .metadata.duration_ms}' /var/log/talos/orchestrator.log

# Track correlation ID through system
CORR_ID="a1b2c3d4e5f67890"
jq --arg id "$CORR_ID" 'select(.correlation_id == $id or .context.parent_correlation_id == $id)' /var/log/talos/*.log

# Memory usage over time
jq -s 'map(select(.metadata.memory_mb) | {timestamp, memory: .metadata.memory_mb})' /var/log/talos/orchestrator.log

# Error rate in last 5 minutes
START=$(date -u -d '5 minutes ago' +%s)
jq --argjson start "$START" 'select(.level == "ERROR" and (split(".")[0] | strptime("%Y-%m-%dT%H:%M:%S") | mktime) >= $start)' /var/log/talos/orchestrator.log | wc -l
```

**Using grep/awk for quick analysis:**

```bash
# Tail logs with color
tail -f /var/log/talos/orchestrator.log | grep --color -E "ERROR|WARN|INFO"

# Count errors per hour
awk '/ERROR/ {print substr($1, 1, 13)}' /var/log/talos/orchestrator.log | sort | uniq -c

# Find unique error types
jq -r 'select(.level == "ERROR" and .error) | .error.code' /var/log/talos/orchestrator.log | sort | uniq -c | sort -rn

# Average response time by endpoint
jq -r 'select(.metadata.duration_ms) | [.context.endpoint, .metadata.duration_ms] | @tsv' /var/log/talos/orchestrator.log | awk '{sum[$1]+=$2; count[$1]++} END {for(e in sum) print e, sum[e]/count[e]}'
```

---

## 4.6 Failure State Reference

### 4.6.1 Common Failure Scenarios

| Scenario | Symptoms | Root Cause | Severity |
|----------|----------|------------|----------|
| Event Loop Block | API unresponsive, health check fails | Long-running sync operation | Critical |
| Memory Exhaustion | OOM kills, slow performance | Memory leak, too many tasks | Critical |
| Database Lock | Write failures, timeouts | Concurrent access, long transaction | High |
| LLM API Down | Task failures, timeouts | External service issue | High |
| Disk Full | Write failures, log errors | Insufficient cleanup | Critical |
| Config Corruption | Startup failures, parse errors | Manual edit error | Critical |
| Network Partition | External API failures | Connectivity issue | Medium |
| SSL Certificate Expiry | HTTPS failures | Certificate not renewed | High |

---

### 4.6.2 Detection Methods

| Failure | Detection Method | Log Pattern | Metric |
|---------|-----------------|-------------|--------|
| Event Loop Block | Watchdog heartbeat timeout | "EVENT LOOP BLOCKED" | event_loop_lag_ms |
| Memory Exhaustion | psutil monitoring | "Memory usage:" | memory_percent |
| Database Lock | Query timeout | "database locked" | db_response_ms |
| LLM API Down | Connection error | "LLM API error" | llm_api_healthy |
| Disk Full | df monitoring | "No space left" | disk_percent |
| Config Corruption | YAML parse error | "Invalid config" | config_valid |
| Network Partition | Ping/HTTP check | "Connection refused" | network_reachable |
| SSL Expiry | Certificate date check | "certificate expired" | ssl_days_remaining |

---

### 4.6.3 Response Procedures

#### F-001: Event Loop Block
```bash
# DETECTION: Watchdog alert "EVENT LOOP BLOCKED"

# IMMEDIATE RESPONSE (within 30s):
# 1. Check if block is resolving
watch -n 1 'curl -s http://localhost:8080/health | jq .checks.orchestrator.block_duration_ms'

# 2. If block persists >30s, container will auto-restart
# 3. Monitor restart
watch -n 5 'docker ps | grep talos'

# POST-RECOVERY:
# 1. Check logs for root cause
grep "block_events" /var/log/talos/block_events.log | tail -1 | jq .

# 2. Review active tasks at time of block
grep "$(date -d '5 min ago' +%Y-%m-%dT%H:%M)" /var/log/talos/orchestrator.log | jq -r '.metadata.task_id'

# 3. If recurring, identify problematic task pattern
```

#### F-002: Memory Exhaustion
```bash
# DETECTION: Memory alert >90%

# IMMEDIATE RESPONSE:
# 1. Identify memory hogs
ps aux --sort=-%mem | head -10

# 2. Check Talos memory breakdown
curl -s http://localhost:8080/metrics/memory | jq .

# 3. If Talos is culprit, trigger graceful restart
curl -X POST http://localhost:8080/admin/restart \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"

# MITIGATION:
# 1. Reduce max concurrent tasks in config
# 2. Enable memory-based task throttling
# 3. Schedule regular restarts during low-traffic
```

#### F-003: Database Lock
```bash
# DETECTION: Database timeout errors

# IMMEDIATE RESPONSE:
# 1. Check for long-running queries
sqlite3 /var/lib/talos/db/talos.db "SELECT * FROM pragma_busy_timeout();"

# 2. Identify locking process
lsof /var/lib/talos/db/talos.db

# 3. If safe, restart Talos to release locks
sudo systemctl restart talos

# PREVENTION:
# 1. Enable WAL mode (if not already)
sqlite3 /var/lib/talos/db/talos.db "PRAGMA journal_mode=WAL;"

# 2. Set busy timeout
sqlite3 /var/lib/talos/db/talos.db "PRAGMA busy_timeout=5000;"

# 3. Review long transactions in code
```

#### F-004: LLM API Down
```bash
# DETECTION: LLM API health check fails

# IMMEDIATE RESPONSE:
# 1. Verify external API status
curl -I https://api.openai.com/v1/models

# 2. Check Talos circuit breaker status
curl -s http://localhost:8080/metrics/circuit_breakers | jq '.llm_api'

# 3. If circuit is open, wait for auto-recovery
#    (default: 60s cooldown)

# FALLBACK:
# 1. Switch to backup LLM provider (if configured)
# 2. Enable offline mode for non-critical tasks
# 3. Queue tasks for retry when API recovers

# MANUAL CIRCUIT RESET (if needed):
curl -X POST http://localhost:8080/admin/circuit-breakers/llm_api/reset \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

#### F-005: Disk Full
```bash
# DETECTION: Disk usage >95%

# IMMEDIATE RESPONSE:
# 1. Identify large files
du -h /var/lib/talos /var/log/talos 2>/dev/null | sort -hr | head -20

# 2. Clear old logs (Tier 2/3 only - NOT audit logs)
find /var/log/talos -name "*.log.*" -mtime +7 -delete

# 3. Clear temporary files
rm -rf /var/lib/talos/tmp/*

# 4. Force log rotation
logrotate -f /etc/logrotate.d/talos

# PREVENTION:
# 1. Enable automated cleanup cron
# 2. Reduce log retention if needed
# 3. Add disk monitoring alert at 80%
```

#### F-006: Config Corruption
```bash
# DETECTION: Startup failure, parse error

# IMMEDIATE RESPONSE:
# 1. Check config syntax
python3 -c "import yaml; yaml.safe_load(open('/etc/talos/config.yaml'))"

# 2. If invalid, restore from backup
sudo cp /etc/talos/config.yaml.backup.$(ls -t /etc/talos/config.yaml.backup.* | head -1) /etc/talos/config.yaml

# 3. Or restore from backup archive
tar -xzf backup.tar.gz -O config/config.yaml > /etc/talos/config.yaml

# 4. Validate and restart
python3 -c "import yaml; yaml.safe_load(open('/etc/talos/config.yaml'))" && sudo systemctl restart talos
```

---

### 4.6.4 Escalation Paths

```
┌─────────────────────────────────────────────────────────────────┐
│                    ESCALATION MATRIX                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Level 1: On-Call Engineer (0-15 min)                          │
│  ─────────────────────────────────────                          │
│  • Acknowledge alert                                            │
│  • Run standard diagnostics                                     │
│  • Apply documented fixes                                       │
│  • Escalate if unresolved after 15 min                          │
│                                                                 │
│  Level 2: Senior Engineer (15-30 min)                          │
│  ─────────────────────────────────────                          │
│  • Complex diagnosis                                            │
│  • Code-level investigation                                     │
│  • Database recovery procedures                                 │
│  • Escalate if unresolved after 30 min                          │
│                                                                 │
│  Level 3: Engineering Lead (30-60 min)                         │
│  ─────────────────────────────────────                          │
│  • Architecture-level decisions                                 │
│  • Data loss risk assessment                                    │
│  • External vendor coordination                                 │
│  • Escalate if unresolved after 60 min                          │
│                                                                 │
│  Level 4: Incident Commander (60+ min)                         │
│  ─────────────────────────────────────                          │
│  • Major incident declaration                                   │
│  • Cross-team coordination                                      │
│  • Customer communication                                       │
│  • Executive briefing                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Escalation Contacts:**
```yaml
escalation:
  level_1:
    pagerduty_key: "${PAGERDUTY_L1_KEY}"
    slack_channel: "#alerts-talos"
  level_2:
    pagerduty_key: "${PAGERDUTY_L2_KEY}"
    slack_channel: "#eng-oncall"
  level_3:
    pagerduty_key: "${PAGERDUTY_L3_KEY}"
    phone: "${LEAD_PHONE}"
  level_4:
    incident_commander: "${IC_PAGERDUTY_KEY}"
    war_room: "#incident-talos"
```

---

## APPENDIX A: Quick Reference Card

### Emergency Commands

```bash
# Check system health
curl -s http://localhost:8080/health | jq .

# Trigger graceful restart
curl -X POST http://localhost:8080/admin/restart -H "Authorization: Bearer ${TOKEN}"

# Trigger panic stop
curl -X POST http://localhost:8080/api/v1/emergency/panic -H "Authorization: Bearer ${TOKEN}"

# Force kill (nuclear option)
sudo kill -9 $(cat /var/run/talos/orchestrator.pid)

# View recent errors
jq 'select(.level == "ERROR")' /var/log/talos/orchestrator.log | tail -20

# Check disk space
df -h /var/lib/talos /var/log/talos

# Check memory
free -h && ps aux --sort=-%mem | head -5

# Database integrity check
sqlite3 /var/lib/talos/db/talos.db "PRAGMA integrity_check;"

# Restore from backup
sudo talos-restore backup.tar.gz --force

# Validate config
python3 -c "import yaml; yaml.safe_load(open('/etc/talos/config.yaml'))"
```

---

## APPENDIX B: Error Code Reference

| Code | Description | Response |
|------|-------------|----------|
| T001 | Config parse error | Fix YAML syntax |
| T002 | Database connection failed | Check DB file permissions |
| T003 | LLM API authentication failed | Verify API key |
| T004 | Task execution timeout | Increase timeout or optimize task |
| T005 | Memory limit exceeded | Reduce concurrent tasks |
| T006 | Disk write failed | Check disk space |
| T007 | Event loop blocked | Restart container |
| T008 | SSL certificate error | Renew certificate |
| T009 | Permission denied | Check file permissions |
| T010 | Circuit breaker open | Wait for cooldown or manual reset |

---

**END OF SECTION 4: Maintainability & Disaster Recovery**

*Document Classification: OPERATIONAL CRITICAL*  
*Last Updated: 2024*  
*Version: 4.0*
