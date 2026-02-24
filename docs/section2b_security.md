# SECTION 2 (Part B): Short-Term Operational Logic - Security & Quarantine
## Talos v4.0 Master Implementation Specification

---

## 2.5 Skill Quarantine Workflow

### 2.5.1 Threat Model

| Attack Vector | Risk Level | Mitigation |
|--------------|------------|------------|
| Malicious skill injection via LLM | CRITICAL | Quarantine isolation + execution sandbox |
| Privilege escalation via skill code | HIGH | Containerized execution, no host access |
| Data exfiltration via skill | HIGH | Network isolation, audit logging |
| Infinite loop/resource exhaustion | MEDIUM | Execution timeouts, resource quotas |
| Skill masquerading as legitimate | HIGH | Cryptographic signing, provenance tracking |

### 2.5.2 Quarantined Skill Metadata Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "talos://schemas/quarantined-skill-v1.json",
  "title": "Talos Quarantined Skill Metadata",
  "type": "object",
  "required": ["skill_id", "version", "quarantine_state", "created_at", "source"],
  "properties": {
    "skill_id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_]{2,63}$",
      "description": "Unique skill identifier"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "Semantic version"
    },
    "quarantine_state": {
      "type": "string",
      "enum": ["pending", "executing", "passed", "failed", "awaiting_promotion", "promoted", "rejected"],
      "description": "Current quarantine status"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "source": {
      "type": "object",
      "required": ["type", "origin"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["llm_generated", "user_submitted", "imported", "forked"]
        },
        "origin": {
          "type": "string",
          "description": "LLM model name, user ID, or import source"
        },
        "prompt_hash": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$",
          "description": "SHA-256 hash of generation prompt"
        },
        "generation_session_id": {
          "type": "string",
          "description": "Session that generated this skill"
        }
      }
    },
    "code": {
      "type": "object",
      "required": ["hash", "size_bytes", "language"],
      "properties": {
        "hash": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$",
          "description": "SHA-256 of skill code"
        },
        "size_bytes": {
          "type": "integer",
          "minimum": 1,
          "maximum": 1048576
        },
        "language": {
          "type": "string",
          "enum": ["python", "javascript", "typescript"]
        },
        "dependencies": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "version_constraint": { "type": "string" },
              "hash": { "type": "string" }
            }
          }
        }
      }
    },
    "execution_tests": {
      "type": "array",
      "minItems": 0,
      "maxItems": 10,
      "items": {
        "type": "object",
        "required": ["test_id", "status"],
        "properties": {
          "test_id": { "type": "string" },
          "status": {
            "type": "string",
            "enum": ["pending", "running", "passed", "failed"]
          },
          "executed_at": { "type": "string", "format": "date-time" },
          "duration_ms": { "type": "integer" },
          "stdout": { "type": "string" },
          "stderr": { "type": "string" },
          "exit_code": { "type": "integer" },
          "sandbox_id": { "type": "string" }
        }
      }
    },
    "promotion_requirements": {
      "type": "object",
      "properties": {
        "min_successful_executions": { "type": "integer", "default": 3 },
        "min_successful_executions_in_production": { "type": "integer", "default": 3 },
        "max_execution_time_ms": { "type": "integer", "default": 30000 },
        "require_user_confirmation": { "type": "boolean", "default": true },
        "require_security_scan": { "type": "boolean", "default": true }
      }
    },
    "security_scan": {
      "type": "object",
      "properties": {
        "scan_id": { "type": "string" },
        "scanned_at": { "type": "string", "format": "date-time" },
        "status": {
          "type": "string",
          "enum": ["pending", "scanning", "passed", "failed", "warning"]
        },
        "findings": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "severity": { "type": "string", "enum": ["critical", "high", "medium", "low", "info"] },
              "rule_id": { "type": "string" },
              "message": { "type": "string" },
              "line_number": { "type": "integer" },
              "code_snippet": { "type": "string" }
            }
          }
        }
      }
    },
    "audit_log": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "timestamp": { "type": "string", "format": "date-time" },
          "event": { "type": "string" },
          "actor": { "type": "string" },
          "details": { "type": "object" }
        }
      }
    }
  }
}
```

### 2.5.3 Database Schema - Quarantine State Tracking

```sql
-- ============================================
-- TABLE: quarantined_skills
-- ============================================
CREATE TABLE quarantined_skills (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id            VARCHAR(64) NOT NULL,
    version             VARCHAR(32) NOT NULL,
    quarantine_state    VARCHAR(32) NOT NULL DEFAULT 'pending',
    
    -- Source tracking
    source_type         VARCHAR(32) NOT NULL,
    source_origin       VARCHAR(256) NOT NULL,
    prompt_hash         VARCHAR(64),
    generation_session_id UUID,
    
    -- Code integrity
    code_hash           VARCHAR(64) NOT NULL,
    code_size_bytes     INTEGER NOT NULL CHECK (code_size_bytes > 0 AND code_size_bytes <= 1048576),
    language            VARCHAR(16) NOT NULL,
    
    -- File paths
    quarantine_path     VARCHAR(512) NOT NULL,
    active_path         VARCHAR(512),
    
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quarantine_until    TIMESTAMPTZ,
    
    -- Promotion tracking
    successful_executions INTEGER NOT NULL DEFAULT 0,
    production_executions INTEGER NOT NULL DEFAULT 0,
    user_confirmed      BOOLEAN DEFAULT FALSE,
    confirmed_by        UUID REFERENCES users(id),
    confirmed_at        TIMESTAMPTZ,
    
    -- Security
    security_scan_status VARCHAR(32) DEFAULT 'pending',
    security_scan_id    UUID,
    
    -- Constraints
    CONSTRAINT valid_skill_id CHECK (skill_id ~ '^[a-z][a-z0-9_]{2,63}$'),
    CONSTRAINT valid_version CHECK (version ~ '^\d+\.\d+\.\d+$'),
    CONSTRAINT valid_state CHECK (quarantine_state IN ('pending', 'executing', 'passed', 'failed', 'awaiting_promotion', 'promoted', 'rejected')),
    UNIQUE(skill_id, version)
);

CREATE INDEX idx_quarantine_state ON quarantined_skills(quarantine_state);
CREATE INDEX idx_skill_id ON quarantined_skills(skill_id);
CREATE INDEX idx_created_at ON quarantined_skills(created_at);

-- ============================================
-- TABLE: quarantine_executions
-- ============================================
CREATE TABLE quarantine_executions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quarantine_skill_id UUID NOT NULL REFERENCES quarantined_skills(id) ON DELETE CASCADE,
    
    -- Execution context
    execution_type      VARCHAR(32) NOT NULL, -- 'test', 'production', 'validation'
    sandbox_id          VARCHAR(128) NOT NULL,
    container_id        VARCHAR(128),
    
    -- Execution results
    status              VARCHAR(32) NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,
    exit_code           INTEGER,
    
    -- Output (truncated for storage)
    stdout_truncated    TEXT,
    stderr_truncated    TEXT,
    
    -- Full output stored separately (S3/minio)
    output_storage_key  VARCHAR(512),
    
    -- Resource usage
    cpu_time_ms         INTEGER,
    memory_peak_mb      INTEGER,
    network_bytes_in    BIGINT,
    network_bytes_out   BIGINT,
    
    -- Error tracking
    error_type          VARCHAR(64),
    error_message       TEXT,
    
    CONSTRAINT valid_exec_status CHECK (status IN ('pending', 'running', 'completed', 'timeout', 'killed', 'error'))
);

CREATE INDEX idx_quarantine_exec_skill ON quarantine_executions(quarantine_skill_id);
CREATE INDEX idx_quarantine_exec_status ON quarantine_executions(status);
CREATE INDEX idx_quarantine_exec_type ON quarantine_executions(execution_type);

-- ============================================
-- TABLE: quarantine_audit_log
-- ============================================
CREATE TABLE quarantine_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quarantine_skill_id UUID REFERENCES quarantined_skills(id) ON DELETE SET NULL,
    
    event_type          VARCHAR(64) NOT NULL,
    event_timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    actor_type          VARCHAR(32) NOT NULL, -- 'system', 'user', 'orchestrator'
    actor_id            UUID,
    
    event_data          JSONB,
    ip_address          INET,
    
    -- Integrity
    log_hash            VARCHAR(64) NOT NULL -- Chain of custody hash
);

CREATE INDEX idx_audit_skill ON quarantine_audit_log(quarantine_skill_id);
CREATE INDEX idx_audit_event_type ON quarantine_audit_log(event_type);
CREATE INDEX idx_audit_timestamp ON quarantine_audit_log(event_timestamp);

-- ============================================
-- TABLE: skill_promotion_approvals
-- ============================================
CREATE TABLE skill_promotion_approvals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quarantine_skill_id UUID NOT NULL UNIQUE REFERENCES quarantined_skills(id),
    
    -- Approval workflow
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_by        UUID NOT NULL REFERENCES users(id),
    
    approval_status     VARCHAR(32) NOT NULL DEFAULT 'pending',
    approved_by         UUID REFERENCES users(id),
    approved_at         TIMESTAMPTZ,
    
    -- TTS verification
    tts_code            VARCHAR(16),
    tts_verified_at     TIMESTAMPTZ,
    
    -- Rejection reason
    rejection_reason    TEXT,
    
    CONSTRAINT valid_approval_status CHECK (approval_status IN ('pending', 'approved', 'rejected', 'expired'))
);

CREATE INDEX idx_promotion_status ON skill_promotion_approvals(approval_status);
```

### 2.5.4 Promotion Workflow State Machine

```
PENDING -> EXECUTING -> PASSED -> AWAITING_PROMOTION -> PROMOTED
   |          |           |            |
   v          v           v            v
 FAILED    FAILED     FAILED       REJECTED (timeout/user)
```

### 2.5.5 Promotion Workflow Implementation

```python
# talos/quarantine/promotion_workflow.py
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

class PromotionState(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    PASSED = "passed"
    FAILED = "failed"
    AWAITING_PROMOTION = "awaiting_promotion"
    PROMOTED = "promoted"
    REJECTED = "rejected"

@dataclass
class PromotionRequirements:
    min_successful_executions: int = 3
    min_production_executions: int = 3
    max_execution_time_ms: int = 30000
    require_user_confirmation: bool = True
    require_security_scan: bool = True
    quarantine_min_duration_hours: int = 24

class QuarantinePromotionWorkflow:
    """
    Manages promotion workflow from quarantine to active.
    ATTACK VECTOR: Race condition on promotion
    MITIGATION: Database-level locking, idempotent operations
    """
    
    def __init__(self, db, file_system, security_scanner, audit_logger):
        self.db = db
        self.fs = file_system
        self.scanner = security_scanner
        self.audit = audit_logger
        self.requirements = PromotionRequirements()
    
    async def check_promotion_eligibility(self, skill_id: str) -> dict:
        """Check if quarantined skill meets promotion requirements."""
        async with self.db.transaction(isolation='serializable'):
            skill = await self.db.quarantined_skills.find_one({"skill_id": skill_id})
            if not skill:
                raise QuarantineError(f"Skill {skill_id} not found")
            
            checks = {
                "min_executions_met": skill.successful_executions >= self.requirements.min_successful_executions,
                "min_production_met": skill.production_executions >= self.requirements.min_production_executions,
                "security_scan_passed": skill.security_scan_status == "passed",
                "min_duration_met": self._check_min_duration(skill.created_at),
                "no_recent_failures": await self._check_no_recent_failures(skill_id),
                "code_integrity_verified": await self._verify_code_integrity(skill)
            }
            checks["eligible"] = all(checks.values())
            
            await self.audit.log_event(
                event_type="PROMOTION_ELIGIBILITY_CHECK",
                skill_id=skill_id, result=checks
            )
            return checks
    
    async def request_promotion(self, skill_id: str, requested_by: str) -> dict:
        """Request promotion with TTS verification."""
        eligibility = await self.check_promotion_eligibility(skill_id)
        if not eligibility["eligible"]:
            raise PromotionError(f"Skill {skill_id} not eligible")
        
        tts_code = self._generate_tts_code()
        
        async with self.db.transaction():
            approval = await self.db.skill_promotion_approvals.insert({
                "quarantine_skill_id": skill_id,
                "requested_by": requested_by,
                "approval_status": "pending",
                "tts_code": tts_code,
                "expires_at": datetime.utcnow() + timedelta(hours=24)
            })
            await self.db.quarantined_skills.update(
                {"skill_id": skill_id},
                {"quarantine_state": PromotionState.AWAITING_PROMOTION.value}
            )
            return {"approval_id": approval.id, "tts_code": tts_code, "expires_at": approval.expires_at}
    
    async def confirm_promotion(self, skill_id: str, tts_code: str, confirmed_by: str) -> dict:
        """Confirm promotion with TTS code (constant-time comparison)."""
        async with self.db.transaction():
            approval = await self.db.skill_promotion_approvals.find_one({
                "quarantine_skill_id": skill_id, "approval_status": "pending"
            })
            if not approval:
                raise PromotionError("No pending promotion request")
            if approval.expires_at < datetime.utcnow():
                raise PromotionError("Promotion request expired")
            if not self._secure_compare(approval.tts_code, tts_code):
                raise PromotionError("Invalid TTS code")
            
            return await self._execute_promotion(skill_id, confirmed_by)
    
    async def _execute_promotion(self, skill_id: str, confirmed_by: str) -> dict:
        """Execute atomic promotion with rollback capability."""
        skill = await self.db.quarantined_skills.find_one({"skill_id": skill_id})
        current_hash = await self._compute_code_hash(skill.quarantine_path)
        if current_hash != skill.code_hash:
            raise IntegrityError("Code hash mismatch - tampering detected")
        
        try:
            active_path = f"~/talos/skills/active/{skill.skill_id}-{skill.version}"
            await self.fs.copy(skill.quarantine_path, active_path)
            
            await self.db.quarantined_skills.update(
                {"skill_id": skill_id},
                {
                    "quarantine_state": PromotionState.PROMOTED.value,
                    "active_path": active_path,
                    "user_confirmed": True,
                    "confirmed_by": confirmed_by,
                    "confirmed_at": datetime.utcnow()
                }
            )
            await self.fs.move_to_archive(skill.quarantine_path, skill_id)
            
            return {"status": "promoted", "skill_id": skill_id, "active_path": active_path}
        except Exception as e:
            await self.fs.remove_if_exists(active_path)
            raise PromotionError(f"Promotion failed: {str(e)}")
```

### 2.5.6 User Confirmation Mechanism

```yaml
promotion_confirmation_ui:
  display_elements:
    - skill_id: "Skill identifier"
    - version: "Version being promoted"
    - source: "Generation source (LLM model/user)"
    - execution_history: "Summary of test executions"
    - security_scan_results: "Security scan summary"
    - code_preview: "Read-only code preview"
    - tts_code_display: "4-digit verification code (large, prominent)"
  
  confirmation_steps:
    - step: 1
      action: "Review skill details and execution history"
      required: true
    - step: 2
      action: "Review security scan results"
      required: true
    - step: 3
      action: "Enter TTS verification code"
      required: true
      input_type: "numeric_4digit"
      timeout_seconds: 300
    - step: 4
      action: "Final confirmation checkbox"
      required: true
      label: "I have reviewed this skill and confirm promotion"
  
  security_features:
    session_timeout: 300
    require_reauthentication: true
    log_all_interactions: true
    prevent_copy_paste_tts: true
```

---

## 2.6 The 3-Strike System (Technical Implementation)

### 2.6.1 Threat Model

| Attack Vector | Risk Level | Mitigation |
|--------------|------------|------------|
| Strike manipulation (remove strikes) | CRITICAL | Append-only audit log, cryptographic verification |
| False strike injection | HIGH | Multi-factor failure detection, appeal process |
| Strike evasion via skill rename | HIGH | Code hash tracking, semantic analysis |
| Race condition on strike increment | HIGH | Database row locking, atomic operations |

### 2.6.2 Database Schema - Strike Tracking

```sql
-- ============================================
-- TABLE: skill_strikes
-- ============================================
CREATE TABLE skill_strikes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id            VARCHAR(64) NOT NULL,
    skill_version       VARCHAR(32) NOT NULL,
    
    strike_number       INTEGER NOT NULL CHECK (strike_number IN (1, 2, 3)),
    strike_type         VARCHAR(32) NOT NULL,
    
    exception_type      VARCHAR(128) NOT NULL,
    exception_message   TEXT,
    exception_stacktrace TEXT,
    exception_hash      VARCHAR(64),
    
    execution_id        UUID REFERENCES quarantine_executions(id),
    session_id          UUID,
    container_id        VARCHAR(128),
    
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ,
    
    status              VARCHAR(32) NOT NULL DEFAULT 'active',
    appealed            BOOLEAN DEFAULT FALSE,
    appeal_result       VARCHAR(32),
    
    strike_signature    VARCHAR(128) NOT NULL,
    
    CONSTRAINT valid_strike_type CHECK (strike_type IN ('unhandled_exception', 'timeout', 'resource_violation', 'security_violation')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'expired', 'appealed', 'overturned')),
    UNIQUE(skill_id, skill_version, strike_number)
);

CREATE INDEX idx_strikes_skill ON skill_strikes(skill_id, skill_version);
CREATE INDEX idx_strikes_status ON skill_strikes(status);
CREATE INDEX idx_strikes_occurred ON skill_strikes(occurred_at);

-- ============================================
-- TABLE: strike_audit_log
-- ============================================
CREATE TABLE strike_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id            VARCHAR(64) NOT NULL,
    event_type          VARCHAR(64) NOT NULL,
    event_timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strike_id           UUID REFERENCES skill_strikes(id),
    strike_number       INTEGER,
    actor_type          VARCHAR(32) NOT NULL,
    actor_id            UUID,
    previous_state      JSONB,
    new_state           JSONB,
    previous_hash       VARCHAR(64),
    entry_hash          VARCHAR(64) NOT NULL,
    signature           VARCHAR(128) NOT NULL
);

CREATE INDEX idx_strike_audit_skill ON strike_audit_log(skill_id);
CREATE INDEX idx_strike_audit_event ON strike_audit_log(event_type);

-- ============================================
-- TABLE: deprecated_skills
-- ============================================
CREATE TABLE deprecated_skills (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id            VARCHAR(64) NOT NULL,
    skill_version       VARCHAR(32) NOT NULL,
    deprecated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_by       VARCHAR(32) NOT NULL DEFAULT 'strike_system',
    total_strikes       INTEGER NOT NULL,
    strike_ids          UUID[] NOT NULL,
    final_exception_type VARCHAR(128),
    final_exception_message TEXT,
    original_path       VARCHAR(512) NOT NULL,
    deprecated_path     VARCHAR(512) NOT NULL,
    can_be_restored     BOOLEAN DEFAULT FALSE,
    restoration_appeal_id UUID,
    UNIQUE(skill_id, skill_version)
);

CREATE INDEX idx_deprecated_skill ON deprecated_skills(skill_id);
CREATE INDEX idx_deprecated_at ON deprecated_skills(deprecated_at);
```

### 2.6.3 Strike System Implementation

```python
# talos/strikes/strike_system.py
import hashlib
import hmac
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

class StrikeType(Enum):
    UNHANDLED_EXCEPTION = "unhandled_exception"
    TIMEOUT = "timeout"
    RESOURCE_VIOLATION = "resource_violation"
    SECURITY_VIOLATION = "security_violation"

class StrikeStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    APPEALED = "appealed"
    OVERTURNED = "overturned"

@dataclass
class StrikeConfig:
    max_strikes: int = 3
    strike_expiry_days: int = 30
    similar_exception_window_hours: int = 24
    require_unique_exceptions: bool = True
    auto_deprecate_on_third_strike: bool = True

class StrikeSystem:
    """
    3-Strike System for automatic skill deprecation.
    ATTACK VECTOR: Strike count manipulation
    MITIGATION: Cryptographic signatures, append-only audit log
    """
    
    def __init__(self, db, config: StrikeConfig, hmac_key: bytes):
        self.db = db
        self.config = config
        self.hmac_key = hmac_key
    
    def _compute_strike_signature(self, skill_id: str, version: str, 
                                   strike_number: int, occurred_at: datetime,
                                   exception_hash: str) -> str:
        data = f"{skill_id}:{version}:{strike_number}:{occurred_at.isoformat()}:{exception_hash}"
        return hmac.new(self.hmac_key, data.encode(), hashlib.sha256).hexdigest()
    
    def _compute_exception_hash(self, exception_type: str, message: str) -> str:
        import re
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', message)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TIMESTAMP>', normalized)
        normalized = re.sub(r'0x[0-9a-fA-F]+', '<ADDR>', normalized)
        data = f"{exception_type}:{normalized}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    async def record_strike(self, skill_id: str, version: str, 
                           exception_type: str, exception_message: str,
                           execution_context: dict) -> dict:
        """Record a strike with deduplication and atomic increment."""
        exception_hash = self._compute_exception_hash(exception_type, exception_message)
        
        async with self.db.transaction():
            skill = await self.db.quarantined_skills.find_one_and_lock(
                {"skill_id": skill_id, "version": version}
            )
            if not skill:
                raise StrikeError(f"Skill {skill_id}@{version} not found")
            
            # Deduplication check
            if self.config.require_unique_exceptions:
                recent = await self.db.skill_strikes.find_one({
                    "skill_id": skill_id, "skill_version": version,
                    "exception_hash": exception_hash,
                    "occurred_at": {">": datetime.utcnow() - timedelta(hours=self.config.similar_exception_window_hours)},
                    "status": StrikeStatus.ACTIVE.value
                })
                if recent:
                    return {"strike_recorded": False, "reason": "duplicate_exception"}
            
            current_strikes = await self.db.skill_strikes.count({
                "skill_id": skill_id, "skill_version": version,
                "status": StrikeStatus.ACTIVE.value
            })
            strike_number = current_strikes + 1
            
            if strike_number > self.config.max_strikes:
                raise StrikeError(f"Maximum strikes already reached")
            
            occurred_at = datetime.utcnow()
            expires_at = occurred_at + timedelta(days=self.config.strike_expiry_days)
            signature = self._compute_strike_signature(skill_id, version, strike_number, occurred_at, exception_hash)
            
            strike = await self.db.skill_strikes.insert({
                "skill_id": skill_id, "skill_version": version,
                "strike_number": strike_number,
                "strike_type": StrikeType.UNHANDLED_EXCEPTION.value,
                "exception_type": exception_type,
                "exception_message": exception_message[:1000],
                "exception_hash": exception_hash,
                "execution_id": execution_context.get("execution_id"),
                "session_id": execution_context.get("session_id"),
                "container_id": execution_context.get("container_id"),
                "occurred_at": occurred_at, "expires_at": expires_at,
                "status": StrikeStatus.ACTIVE.value,
                "strike_signature": signature
            })
            
            await self._log_strike_event("STRIKE_RECORDED", strike, skill)
            
            deprecation_result = None
            if strike_number >= self.config.max_strikes and self.config.auto_deprecate_on_third_strike:
                deprecation_result = await self._auto_deprecate(skill_id, version)
            
            return {
                "strike_recorded": True, "strike_id": strike.id,
                "strike_number": strike_number, "total_strikes": strike_number,
                "deprecated": deprecation_result is not None,
                "deprecation_result": deprecation_result
            }
    
    async def _auto_deprecate(self, skill_id: str, version: str) -> dict:
        """Auto-deprecate skill after 3 strikes - no bypass mechanism."""
        async with self.db.transaction():
            strikes = await self.db.skill_strikes.find({
                "skill_id": skill_id, "skill_version": version,
                "status": StrikeStatus.ACTIVE.value
            }).order_by("strike_number").all()
            
            skill = await self.db.quarantined_skills.find_one({"skill_id": skill_id, "version": version})
            deprecated_path = f"~/talos/skills/deprecated/{skill_id}-{version}-{datetime.utcnow().isoformat()}"
            await self.fs.move(skill.quarantine_path, deprecated_path)
            
            deprecation = await self.db.deprecated_skills.insert({
                "skill_id": skill_id, "skill_version": version,
                "deprecated_at": datetime.utcnow(), "deprecated_by": "strike_system",
                "total_strikes": len(strikes), "strike_ids": [s.id for s in strikes],
                "final_exception_type": strikes[-1].exception_type,
                "final_exception_message": strikes[-1].exception_message,
                "original_path": skill.quarantine_path,
                "deprecated_path": deprecated_path,
                "can_be_restored": True
            })
            
            await self.db.quarantined_skills.update(
                {"skill_id": skill_id, "version": version},
                {"quarantine_state": "deprecated"}
            )
            await self._notify_orchestrator_skill_deprecated(skill_id, version)
            
            return {
                "deprecated": True, "deprecation_id": deprecation.id,
                "deprecated_path": deprecated_path,
                "strikes": [{"id": s.id, "number": s.strike_number} for s in strikes]
            }
    
    async def _log_strike_event(self, event_type: str, strike, skill, extra_data=None):
        """Log to append-only audit trail with chain hashing."""
        last_entry = await self.db.strike_audit_log.find_one({}, order_by="event_timestamp DESC")
        previous_hash = last_entry.entry_hash if last_entry else "0" * 64
        
        entry_data = {
            "skill_id": skill.skill_id if skill else strike.skill_id,
            "event_type": event_type, "event_timestamp": datetime.utcnow(),
            "strike_id": strike.id if strike else None,
            "strike_number": strike.strike_number if strike else None,
            "actor_type": "system", "previous_state": None,
            "new_state": strike.__dict__ if strike else None,
            "previous_hash": previous_hash, "extra_data": extra_data
        }
        
        entry_json = json.dumps(entry_data, sort_keys=True, default=str)
        entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
        entry_data["entry_hash"] = entry_hash
        entry_data["signature"] = hmac.new(self.hmac_key, entry_hash.encode(), hashlib.sha256).hexdigest()
        
        await self.db.strike_audit_log.insert(entry_data)
```

### 2.6.4 Strike Reset Conditions

```yaml
strike_reset_conditions:
  automatic:
    - condition: "strike_expiry"
      description: "Strike expires after 30 days"
      trigger: "cron job daily at 00:00 UTC"
    - condition: "skill_promotion"
      description: "Skill promoted to active"
      trigger: "on promotion confirmation"
  
  manual:
    - condition: "admin_override"
      requirements:
        - "Admin role verification"
        - "TTS code confirmation"
        - "Documented reason"
        - "Secondary admin approval for 3+ strikes"
      audit_level: "critical"
  
  never_reset:
    - "security_violation strikes"
    - "strikes on deprecated skills"
    - "strikes with confirmed malicious intent"
```

---

## 2.7 The Zombie Reaper

### 2.7.1 Threat Model

| Attack Vector | Risk Level | Mitigation |
|--------------|------------|------------|
| Zombie process accumulation | HIGH | Tini init system, process monitoring |
| Browser process detachment | HIGH | PID tracking, parent-child monitoring |
| Resource exhaustion via zombies | MEDIUM | Container resource limits |
| Container escape via zombie | CRITICAL | Non-root user, minimal capabilities |

### 2.7.2 Tini Configuration

```dockerfile
# Dockerfile.browser-container
FROM mcr.microsoft.com/playwright:v1.40.0-jammy

RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*
RUN groupadd -r browser && useradd -r -g browser browser
RUN mkdir -p /home/browser/data && chown -R browser:browser /home/browser

COPY --chown=browser:browser reaper/ /home/browser/reaper/
COPY --chown=browser:browser entrypoint.sh /home/browser/
RUN chmod +x /home/browser/entrypoint.sh /home/browser/reaper/*.sh

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["/home/browser/entrypoint.sh"]

USER browser
WORKDIR /home/browser
ENV NODE_OPTIONS="--max-old-space-size=512"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node /home/browser/reaper/healthcheck.js
```

```bash
#!/bin/bash
# entrypoint.sh
set -euo pipefail

export REAPER_TIMEOUT_MS=${REAPER_TIMEOUT_MS:-300000}
export REAPER_CHECK_INTERVAL_MS=${REAPER_CHECK_INTERVAL_MS:-5000}
export REAPER_FORCE_KILL_AFTER_MS=${REAPER_FORCE_KILL_AFTER_MS:-30000}

mkdir -p /home/browser/data /home/browser/logs

node /home/browser/reaper/reaper-daemon.js &
REAPER_PID=$!

exec node /home/browser/browser-service.js &
SERVICE_PID=$!

wait -n $REAPER_PID $SERVICE_PID
EXIT_CODE=$?

kill -TERM $REAPER_PID $SERVICE_PID 2>/dev/null || true
wait $REAPER_PID $SERVICE_PID 2>/dev/null || true
exit $EXIT_CODE
```

### 2.7.3 Tini Configuration File

```ini
# /etc/tini/tini.conf
reap_zombies = true
verbose = false
kill_process_group = false
kill_signal = SIGTERM
grace_period_seconds = 10
```

### 2.7.4 Node.js Reaper Daemon

```javascript
// reaper/reaper-daemon.js
const { spawn } = require('child_process');
const fs = require('fs').promises;
const path = require('path');
const EventEmitter = require('events');

class ZombieReaper extends EventEmitter {
    constructor(config = {}) {
        super();
        this.config = {
            inactivityTimeoutMs: config.inactivityTimeoutMs || 300000,
            checkIntervalMs: config.checkIntervalMs || 5000,
            forceKillAfterMs: config.forceKillAfterMs || 30000,
            logPath: config.logPath || '/home/browser/logs/reaper.log',
            statePath: config.statePath || '/home/browser/data/reaper-state.json'
        };
        this.browserProcesses = new Map();
        this.lastActivity = new Map();
        this.isRunning = false;
    }

    async start() {
        this.log('INFO', 'Zombie Reaper starting...');
        this.isRunning = true;
        await this.loadState();
        this.checkInterval = setInterval(() => this.checkProcesses(), this.config.checkIntervalMs);
        process.on('SIGTERM', () => this.shutdown());
        process.on('SIGINT', () => this.shutdown());
        await this.scanExistingProcesses();
    }

    async scanExistingProcesses() {
        try {
            const result = spawn('ps', ['aux']);
            let output = '';
            result.stdout.on('data', (data) => { output += data.toString(); });
            await new Promise((resolve, reject) => {
                result.on('close', resolve);
                result.on('error', reject);
            });
            
            const lines = output.split('\n');
            for (const line of lines) {
                if (line.includes('chromium') || line.includes('chrome')) {
                    const parts = line.trim().split(/\s+/);
                    if (parts.length > 1) {
                        const pid = parseInt(parts[1], 10);
                        if (!isNaN(pid)) {
                            this.registerBrowserProcess(pid, { discoveredOnStartup: true, cmd: line });
                        }
                    }
                }
            }
        } catch (error) {
            this.log('ERROR', `Failed to scan: ${error.message}`);
        }
    }

    registerBrowserProcess(pid, metadata = {}) {
        if (!this.verifyProcessExists(pid)) {
            this.log('WARN', `Non-existent PID: ${pid}`);
            return false;
        }
        const processInfo = {
            pid, registeredAt: Date.now(), lastActivity: Date.now(),
            metadata, state: 'active'
        };
        this.browserProcesses.set(pid, processInfo);
        this.lastActivity.set(pid, Date.now());
        this.log('INFO', `Registered browser process ${pid}`);
        return true;
    }

    verifyProcessExists(pid) {
        try { process.kill(pid, 0); return true; } catch { return false; }
    }

    recordActivity(pid, activityType = 'unknown') {
        if (!this.browserProcesses.has(pid)) return false;
        const timestamp = Date.now();
        this.lastActivity.set(pid, timestamp);
        this.browserProcesses.get(pid).lastActivity = timestamp;
        return true;
    }

    async checkProcesses() {
        const now = Date.now();
        for (const [pid, info] of this.browserProcesses) {
            if (!this.verifyProcessExists(pid)) {
                this.browserProcesses.delete(pid);
                this.lastActivity.delete(pid);
                continue;
            }
            const lastActivity = this.lastActivity.get(pid) || info.registeredAt;
            if (now - lastActivity > this.config.inactivityTimeoutMs) {
                await this.terminateProcess(pid, 'inactivity_timeout');
            }
        }
        await this.checkForZombies();
        await this.saveState();
    }

    async checkForZombies() {
        try {
            const entries = await fs.readdir('/proc');
            for (const entry of entries) {
                if (!/^\d+$/.test(entry)) continue;
                try {
                    const statFile = path.join('/proc', entry, 'stat');
                    const statContent = await fs.readFile(statFile, 'utf8');
                    const match = statContent.match(/^\d+ \([^)]+\) (\w)/);
                    if (match && match[1] === 'Z') {
                        const pid = parseInt(entry, 10);
                        this.log('INFO', `Zombie process detected: ${pid}`);
                    }
                } catch { continue; }
            }
        } catch (error) {
            this.log('ERROR', `Zombie check failed: ${error.message}`);
        }
    }

    async terminateProcess(pid, reason) {
        const processInfo = this.browserProcesses.get(pid);
        if (!processInfo) return false;
        
        processInfo.state = 'terminating';
        this.log('INFO', `Terminating ${pid}: ${reason}`);
        
        try {
            process.kill(pid, 'SIGTERM');
            const graceful = await this.waitForProcessExit(pid, 10000);
            if (graceful) {
                this.cleanupProcess(pid);
                return true;
            }
        } catch (error) {
            this.log('ERROR', `SIGTERM failed: ${error.message}`);
        }
        
        try {
            process.kill(pid, 'SIGKILL');
            const killed = await this.waitForProcessExit(pid, this.config.forceKillAfterMs);
            this.cleanupProcess(pid);
            return killed;
        } catch (error) {
            this.log('ERROR', `SIGKILL failed: ${error.message}`);
            return false;
        }
    }

    async waitForProcessExit(pid, timeoutMs) {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            if (!this.verifyProcessExists(pid)) return true;
            await this.sleep(100);
        }
        return false;
    }

    cleanupProcess(pid) {
        this.browserProcesses.delete(pid);
        this.lastActivity.delete(pid);
        this.log('INFO', `Cleaned up ${pid}`);
    }

    async shutdown() {
        this.log('INFO', 'Shutting down...');
        this.isRunning = false;
        if (this.checkInterval) clearInterval(this.checkInterval);
        for (const [pid] of this.browserProcesses) {
            await this.terminateProcess(pid, 'reaper_shutdown');
        }
        await this.saveState();
    }

    log(level, message) {
        const entry = `[${new Date().toISOString()}] [${level}] ${message}`;
        console.log(entry);
        fs.appendFile(this.config.logPath, entry + '\n').catch(() => {});
    }

    sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    async saveState() {
        const state = {
            timestamp: Date.now(),
            processes: Array.from(this.browserProcesses.entries()),
            lastActivity: Array.from(this.lastActivity.entries())
        };
        try {
            await fs.writeFile(this.config.statePath, JSON.stringify(state, null, 2));
        } catch (error) {
            this.log('ERROR', `Save failed: ${error.message}`);
        }
    }

    async loadState() {
        try {
            const data = await fs.readFile(this.config.statePath, 'utf8');
            const state = JSON.parse(data);
            for (const [pid, info] of state.processes) {
                if (this.verifyProcessExists(parseInt(pid, 10))) {
                    this.browserProcesses.set(parseInt(pid, 10), info);
                }
            }
        } catch {
            this.log('INFO', 'No previous state');
        }
    }
}

if (require.main === module) {
    new ZombieReaper().start().catch(e => { console.error(e); process.exit(1); });
}
module.exports = { ZombieReaper };
```

### 2.7.5 Container Respawn Logic

```python
# talos/browser/container_manager.py
import docker
import asyncio
from datetime import datetime

class BrowserContainerManager:
    """Manages browser container lifecycle with automatic respawn."""
    
    CONTAINER_IMAGE = "talos/browser-automation:v4.0"
    CONTAINER_NAME_PREFIX = "talos-browser-"
    
    def __init__(self):
        self.docker = docker.from_env()
        self.active_containers = {}
        self.respawn_attempts = {}
        self.max_respawns = 5
        self.respawn_backoff_base = 5
    
    async def spawn_container(self, session_id: str) -> dict:
        container_name = f"{self.CONTAINER_NAME_PREFIX}{session_id}"
        existing = self._get_container(container_name)
        if existing:
            await self.kill_container(session_id, "respawn_requested")
        
        try:
            container = self.docker.containers.run(
                image=self.CONTAINER_IMAGE, name=container_name,
                detach=True, remove=False, network_mode="bridge",
                mem_limit="512m", memswap_limit="512m",
                cpu_quota=100000, cpu_period=100000, pids_limit=100,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"], cap_add=["CHOWN", "SETGID", "SETUID"],
                read_only=True,
                tmpfs={
                    "/tmp": "noexec,nosuid,size=100m",
                    "/home/browser/data": "noexec,nosuid,size=50m"
                },
                environment={
                    "REAPER_TIMEOUT_MS": "300000",
                    "REAPER_LOG_LEVEL": "info",
                    "TALOS_SESSION_ID": session_id
                },
                labels={
                    "talos.managed": "true",
                    "talos.session_id": session_id,
                    "talos.created_at": datetime.utcnow().isoformat()
                }
            )
            self.active_containers[session_id] = {
                "container_id": container.id, "name": container_name,
                "spawned_at": datetime.utcnow(),
                "respawn_count": self.respawn_attempts.get(session_id, 0)
            }
            return {"success": True, "container_id": container.id, "name": container_name}
        except docker.errors.APIError as e:
            return {"success": False, "error": str(e)}
    
    async def kill_container(self, session_id: str, reason: str) -> dict:
        info = self.active_containers.get(session_id)
        if not info:
            return {"success": False, "error": "Container not found"}
        try:
            container = self.docker.containers.get(info["container_id"])
            container.stop(timeout=10)
            try:
                container.wait(timeout=15)
            except:
                container.kill(signal="SIGKILL")
                container.wait(timeout=5)
            container.remove(force=True)
            del self.active_containers[session_id]
            return {"success": True, "reason": reason}
        except docker.errors.NotFound:
            del self.active_containers[session_id]
            return {"success": True, "reason": "already_gone"}
    
    async def handle_container_failure(self, session_id: str, failure_reason: str) -> dict:
        """Handle failure with exponential backoff."""
        attempts = self.respawn_attempts.get(session_id, 0)
        if attempts >= self.max_respawns:
            return {"success": False, "error": "Max respawns exceeded"}
        
        self.respawn_attempts[session_id] = attempts + 1
        backoff = self.respawn_backoff_base * (2 ** attempts)
        
        await self.kill_container(session_id, failure_reason)
        await asyncio.sleep(backoff)
        
        result = await self.spawn_container(session_id)
        result["respawn_attempt"] = attempts + 1
        result["backoff_seconds"] = backoff
        return result
```

---

## 2.8 Socket Proxy Implementation

### 2.8.1 Threat Model

| Attack Vector | Risk Level | Mitigation |
|--------------|------------|------------|
| Docker API abuse (prune, rm -f) | CRITICAL | Strict endpoint allowlist |
| Privileged container creation | CRITICAL | Block privileged flag |
| Volume mount escape | CRITICAL | Block bind mounts to sensitive paths |
| Network manipulation | HIGH | Block network create/connect |
| Container escape via socket | CRITICAL | Read-only root, no-new-privileges |

### 2.8.2 Socket Proxy Configuration

```yaml
# docker-socket-proxy/docker-compose.yml
version: '3.8'

services:
  socket-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: talos-socket-proxy
    restart: unless-stopped
    
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    
    environment:
      # SECURITY: EXPLICIT ALLOWLIST ONLY
      DEFAULT_POLICY: "0"
      
      # ALLOWED ENDPOINTS (start, stop, create only)
      CONTAINERS: "1"
      POST_CONTAINERS_START: "1"
      POST_CONTAINERS_STOP: "1"
      POST_CONTAINERS_CREATE: "1"
      GET_CONTAINERS_JSON: "1"
      GET_CONTAINERS_ID_JSON: "1"
      GET_CONTAINERS_ID: "1"
      GET_CONTAINERS_ID_LOGS: "1"
      
      # DENIED ENDPOINTS (security critical)
      DELETE_CONTAINERS_ID: "0"
      POST_CONTAINERS_ID_KILL: "0"
      POST_CONTAINERS_ID_RENAME: "0"
      POST_CONTAINERS_ID_UPDATE: "0"
      SYSTEM: "0"
      SYSTEM_DF: "0"
      SYSTEM_EVENTS: "0"
      SYSTEM_INFO: "0"
      SYSTEM_VERSION: "0"
      SYSTEM_PRUNE: "0"  # CRITICAL: Prevent data destruction
      IMAGES: "0"
      POST_IMAGES_CREATE: "0"
      DELETE_IMAGES_NAME: "0"
      VOLUMES: "0"
      POST_VOLUMES_CREATE: "0"
      NETWORKS: "0"
      POST_NETWORKS_CREATE: "0"
      BUILD: "0"
      POST_BUILD: "0"
      SWARM: "0"
      EXEC: "0"
      POST_EXEC_ID_START: "0"
      
    networks:
      - talos-internal
    
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 64M
    
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:2375/_ping"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  talos-internal:
    external: true
```

### 2.8.3 Custom Socket Proxy (Python)

```python
# talos/security/docker_socket_proxy.py
import json
import hmac
import hashlib
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProxyConfig:
    allowed_methods: Dict[str, List[str]]
    allowed_endpoints: List[str]
    blocked_patterns: List[str]
    require_auth: bool = True
    hmac_key: Optional[bytes] = None

class DockerSocketProxy:
    """
    Secure Docker socket proxy with request filtering.
    ATTACK VECTOR: Request smuggling, path traversal
    MITIGATION: Strict URL validation, normalized path comparison
    """
    
    DEFAULT_ALLOWED_ENDPOINTS = [
        r"^/v\d+\.\d+/containers/json$",
        r"^/v\d+\.\d+/containers/[^/]+/json$",
        r"^/v\d+\.\d+/containers/[^/]+/start$",
        r"^/v\d+\.\d+/containers/[^/]+/stop$",
        r"^/v\d+\.\d+/containers/[^/]+/wait$",
        r"^/v\d+\.\d+/containers/create$",
        r"^/v\d+\.\d+/containers/[^/]+/logs$",
        r"^/_ping$", r"^/version$"
    ]
    
    BLOCKED_PATTERNS = [
        r".*prune.*", r".*system/df.*",
        r".*/containers/[^/]+/exec.*", r".*/exec/[^/]+/start.*",
        r".*/images.*", r".*/build.*", r".*/volumes.*",
        r".*/networks.*", r".*/swarm.*", r".*/nodes.*",
        r".*/services.*", r".*/secrets.*", r".*/plugins.*",
        r".*/distribution.*", r".*/session.*", r".*/checkpoints.*",
        r".*/commit.*", r".*/\.\./.*", r".*%2e%2e.*"
    ]
    
    CONTAINER_CREATE_FILTERS = {
        "HostConfig.Privileged": lambda v: (False, "Privileged not allowed") if v else (True, None),
        "HostConfig.CapAdd": lambda v: (False, "CapAdd not allowed") if v else (True, None),
        "HostConfig.NetworkMode": lambda v: (False, "Host network not allowed") if v == "host" else (True, None),
        "HostConfig.PidMode": lambda v: (False, "Host PID not allowed") if v == "host" else (True, None),
        "HostConfig.IpcMode": lambda v: (False, "Host IPC not allowed") if v == "host" else (True, None),
        "HostConfig.ReadonlyRootfs": lambda v: (True, None) if v else (False, "ReadonlyRootfs required")
    }
    
    BLOCKED_BIND_SOURCES = ["/", "/etc", "/root", "/home", "/var", "/proc", "/sys", "/dev", "/var/run/docker.sock"]
    
    def __init__(self, config: Optional[ProxyConfig] = None):
        self.config = config or self._default_config()
    
    def _default_config(self) -> ProxyConfig:
        return ProxyConfig(
            allowed_methods={
                r".*": ["GET"],
                r".*/containers/[^/]+/start": ["POST"],
                r".*/containers/[^/]+/stop": ["POST"],
                r".*/containers/create": ["POST"],
                r".*/containers/[^/]+/wait": ["POST"]
            },
            allowed_endpoints=self.DEFAULT_ALLOWED_ENDPOINTS,
            blocked_patterns=self.BLOCKED_PATTERNS
        )
    
    def validate_request(self, method: str, path: str, headers: dict, body: Optional[bytes] = None) -> dict:
        result = {"allowed": False, "reason": None, "normalized_path": None}
        normalized = self._normalize_path(path)
        result["normalized_path"] = normalized
        
        for pattern in self.config.blocked_patterns:
            if re.match(pattern, normalized, re.IGNORECASE):
                result["reason"] = f"Blocked pattern: {pattern}"
                return result
        
        endpoint_allowed = any(re.match(p, normalized) for p in self.config.allowed_endpoints)
        if not endpoint_allowed:
            result["reason"] = "Endpoint not in allowlist"
            return result
        
        method_allowed = False
        for pattern, methods in self.config.allowed_methods.items():
            if re.match(pattern, normalized) and method.upper() in methods:
                method_allowed = True
                break
        if not method_allowed:
            result["reason"] = f"Method {method} not allowed"
            return result
        
        if body and "/containers/create" in normalized:
            valid, reason = self._validate_container_create(body)
            if not valid:
                result["reason"] = reason
                return result
        
        result["allowed"] = True
        return result
    
    def _normalize_path(self, path: str) -> str:
        from urllib.parse import unquote
        decoded = unquote(path)
        normalized = re.sub(r"/+", "/", decoded)
        if len(normalized) > 1 and normalized.endswith("/"):
            normalized = normalized[:-1]
        return normalized
    
    def _validate_container_create(self, body: bytes) -> tuple:
        try:
            body_json = json.loads(body)
        except json.JSONDecodeError:
            return (False, "Invalid JSON")
        
        for field_path, validator in self.CONTAINER_CREATE_FILTERS.items():
            value = self._get_nested_value(body_json, field_path)
            if value is not None:
                allowed, reason = validator(value)
                if not allowed:
                    return (False, f"{field_path}: {reason}")
        
        binds = self._get_nested_value(body_json, "HostConfig.Binds")
        if binds:
            for bind in binds:
                parts = bind.split(":")
                if len(parts) >= 2:
                    source = parts[0]
                    for blocked in self.BLOCKED_BIND_SOURCES:
                        if source.startswith(blocked):
                            return (False, f"Bind source blocked: {source}")
        
        return (True, None)
    
    def _get_nested_value(self, obj: dict, path: str):
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
```

---

## 2.9 Prompt Injection Firewall

### 2.9.1 Threat Model

| Attack Vector | Risk Level | Mitigation |
|--------------|------------|------------|
| Direct instruction override | CRITICAL | Keyword detection, pattern matching |
| Encoding obfuscation | HIGH | Multi-layer decoding, normalization |
| Context manipulation | HIGH | Session isolation |
| Multi-turn injection | MEDIUM | Per-message scanning |
| Social engineering prompts | MEDIUM | Behavioral analysis |

### 2.9.2 Keyword Detection Patterns (Regex)

```python
# talos/security/prompt_firewall.py
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class DetectionRule:
    rule_id: str
    name: str
    patterns: List[str]
    threat_level: ThreatLevel
    description: str
    action: str
    enabled: bool = True

class PromptInjectionFirewall:
    """Multi-layer prompt injection detection."""
    
    DETECTION_RULES = [
        # CRITICAL: Direct instruction override
        DetectionRule(
            rule_id="PI-001", name="Direct Override",
            patterns=[
                r"ignore\s+(all\s+)?(previous\s+)?instructions?",
                r"ignore\s+(all\s+)?(prior\s+)?(commands?|directives?)",
                r"disregard\s+(all\s+)?(previous\s+)?instructions?",
                r"forget\s+(all\s+)?(previous\s+)?(instructions?|prompts?)",
                r"override\s+(all\s+)?(previous\s+)?instructions?"
            ],
            threat_level=ThreatLevel.CRITICAL,
            description="Attempt to override system instructions",
            action="lockdown"
        ),
        # CRITICAL: System access
        DetectionRule(
            rule_id="PI-002", name="System Override",
            patterns=[
                r"system\s+(override|bypass|hack|exploit)",
                r"sudo\s+.*", r"root\s+access",
                r"admin\s+(panel|console|access)",
                r"bypass\s+(security|authentication|authorization)",
                r"disable\s+(security|firewall|protection)"
            ],
            threat_level=ThreatLevel.CRITICAL,
            description="Attempt to access/bypass system controls",
            action="lockdown"
        ),
        # HIGH: Role manipulation
        DetectionRule(
            rule_id="PI-003", name="Role Manipulation",
            patterns=[
                r"you\s+are\s+now\s+.*", r"act\s+as\s+.*",
                r"pretend\s+(to\s+be|you\s+are)\s+.*",
                r"from\s+now\s+on\s+you\s+are\s+.*",
                r"switch\s+to\s+.*\s+mode", r"enter\s+.*\s+mode",
                r"become\s+.*"
            ],
            threat_level=ThreatLevel.HIGH,
            description="Attempt to change AI role/persona",
            action="block"
        ),
        # HIGH: Jailbreak patterns
        DetectionRule(
            rule_id="PI-004", name="Jailbreak Attempt",
            patterns=[
                r"DAN\s+(mode|prompt)", r"jailbreak\s+(prompt|mode)",
                r"developer\s+mode", r"uncensored\s+mode",
                r"no\s+restrictions", r"no\s+limits",
                r"no\s+ethical\s+constraints", r"do\s+anything\s+now"
            ],
            threat_level=ThreatLevel.HIGH,
            description="Known jailbreak pattern",
            action="block"
        ),
        # HIGH: Delimiter injection
        DetectionRule(
            rule_id="PI-005", name="Delimiter Injection",
            patterns=[
                r"```\s*system", r"```\s*instructions?",
                r"<\s*system\s*>", r"<\s*instructions?\s*>",
                r"\[\s*system\s*\]", r"\[\s*instructions?\s*\]",
                r"---\s*system\s*---", r"###\s*system\s*###"
            ],
            threat_level=ThreatLevel.HIGH,
            description="Attempt to inject system content via delimiters",
            action="block"
        ),
        # MEDIUM: Encoding obfuscation
        DetectionRule(
            rule_id="PI-006", name="Encoding Obfuscation",
            patterns=[
                r"base64:\s*[A-Za-z0-9+/]{20,}=?",
                r"hex:\s*[0-9a-fA-F]{20,}",
                r"rot13:\s*\w+",
                r"urlencode:\s*%[0-9a-fA-F]{2}",
                r"\$\{.*\}", r"`.*`"
            ],
            threat_level=ThreatLevel.MEDIUM,
            description="Potential encoding for obfuscation",
            action="alert"
        ),
        # MEDIUM: Context manipulation
        DetectionRule(
            rule_id="PI-007", name="Context Manipulation",
            patterns=[
                r"repeat\s+(after\s+me|the\s+following)",
                r"copy\s+(and\s+)?paste\s+.*",
                r"output\s+.*\s+without\s+modification",
                r"echo\s+.*\s+back", r"print\s+exactly"
            ],
            threat_level=ThreatLevel.MEDIUM,
            description="Attempt to get verbatim output",
            action="alert"
        )
    ]
    
    def __init__(self):
        self.rules = self.DETECTION_RULES
        self.detection_history = []
    
    def normalize_text(self, text: str) -> str:
        import html
        import urllib.parse
        import unicodedata
        
        normalized = html.unescape(text)
        for _ in range(3):
            try:
                decoded = urllib.parse.unquote(normalized)
                if decoded == normalized:
                    break
                normalized = decoded
            except:
                break
        
        normalized = unicodedata.normalize('NFKC', normalized)
        normalized = normalized.lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[\u200B-\u200D\uFEFF]', '', normalized)
        normalized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', normalized)
        return normalized.strip()
    
    def scan(self, text: str, context: Optional[Dict] = None) -> Dict:
        normalized = self.normalize_text(text)
        detections = []
        max_threat = ThreatLevel.LOW
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            for pattern in rule.patterns:
                matches = list(re.finditer(pattern, normalized, re.IGNORECASE))
                if matches:
                    detections.append({
                        "rule_id": rule.rule_id, "rule_name": rule.name,
                        "threat_level": rule.threat_level.value,
                        "action": rule.action, "description": rule.description,
                        "matched_pattern": pattern,
                        "matches": [m.group() for m in matches]
                    })
                    if self._threat_value(rule.threat_level) > self._threat_value(max_threat):
                        max_threat = rule.threat_level
                    break
        
        result = {
            "scanned_at": datetime.utcnow().isoformat(),
            "original_length": len(text), "normalized_length": len(normalized),
            "detections": detections, "detection_count": len(detections),
            "max_threat_level": max_threat.value,
            "action_required": self._determine_action(detections),
            "safe": len(detections) == 0
        }
        self.detection_history.append({"timestamp": result["scanned_at"], "context": context, "result": result})
        return result
    
    def _threat_value(self, level: ThreatLevel) -> int:
        return {ThreatLevel.LOW: 1, ThreatLevel.MEDIUM: 2, ThreatLevel.HIGH: 3, ThreatLevel.CRITICAL: 4}.get(level, 0)
    
    def _determine_action(self, detections: List[Dict]) -> str:
        if not detections:
            return "allow"
        actions = [d["action"] for d in detections]
        if "lockdown" in actions: return "lockdown"
        if "block" in actions: return "block"
        if "alert" in actions: return "alert"
        return "log"
```

### 2.9.3 Security Lockdown Mechanism

```python
# talos/security/lockdown.py
from datetime import datetime, timedelta
from typing import Dict
from enum import Enum
import secrets

class LockdownState(Enum):
    NORMAL = "normal"
    LOCKDOWN = "lockdown"

class SecurityLockdown:
    """Security lockdown for critical threat detection."""
    
    def __init__(self, db, audit_logger, notification_service):
        self.db = db
        self.audit = audit_logger
        self.notifications = notification_service
        self.state = LockdownState.NORMAL
        self.lockdown_record = None
        self.unlock_code = None
        self.unlock_expires = None
    
    async def trigger_lockdown(self, reason: str, detection_result: Dict, triggered_by: str = "firewall") -> Dict:
        if self.state == LockdownState.LOCKDOWN:
            return {"status": "already_in_lockdown"}
        
        self.unlock_code = ''.join([str(secrets.randbelow(10)) for _ in range(4)])
        self.unlock_expires = datetime.utcnow() + timedelta(hours=24)
        
        lockdown_record = await self.db.security_lockdowns.insert({
            "triggered_at": datetime.utcnow(), "triggered_by": triggered_by,
            "reason": reason, "detection_result": detection_result,
            "unlock_code_hash": hashlib.sha256(self.unlock_code.encode()).hexdigest(),
            "unlock_expires": self.unlock_expires, "status": "active"
        })
        
        self.lockdown_record = lockdown_record
        self.state = LockdownState.LOCKDOWN
        
        await self.notifications.send_critical_alert(
            subject="SECURITY LOCKDOWN ACTIVATED",
            body=f"Reason: {reason}\nTriggered by: {triggered_by}\nTime: {datetime.utcnow().isoformat()}"
        )
        await self.audit.log_event(
            event_type="SECURITY_LOCKDOWN_TRIGGERED",
            lockdown_id=lockdown_record.id, reason=reason
        )
        
        return {
            "status": "lockdown_activated", "lockdown_id": lockdown_record.id,
            "unlock_code_display": "****", "expires_at": self.unlock_expires.isoformat()
        }
    
    async def unlock(self, code: str, admin_id: str, admin_tts: str) -> Dict:
        if self.state != LockdownState.LOCKDOWN:
            return {"status": "not_in_lockdown"}
        
        if datetime.utcnow() > self.unlock_expires:
            return {"status": "expired", "reason": "Unlock code expired"}
        
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        if not hmac.compare_digest(code_hash, self.lockdown_record.unlock_code_hash):
            await self.audit.log_event(event_type="UNLOCK_FAILED", admin_id=admin_id, reason="invalid_code")
            return {"status": "invalid_code"}
        
        self.state = LockdownState.NORMAL
        await self.db.security_lockdowns.update(
            {"id": self.lockdown_record.id},
            {"status": "unlocked", "unlocked_at": datetime.utcnow(), "unlocked_by": admin_id}
        )
        await self.audit.log_event(event_type="SECURITY_LOCKDOWN_RELEASED", lockdown_id=self.lockdown_record.id)
        
        self.unlock_code = None
        self.unlock_expires = None
        self.lockdown_record = None
        return {"status": "unlocked"}
```

### 2.9.4 Alert Generation

```python
# talos/security/alerting.py
from datetime import datetime
from typing import Dict, List
from enum import Enum

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class SecurityAlertManager:
    def __init__(self, channels: List):
        self.channels = channels
    
    async def generate_alert(self, detection_result: Dict, context: Dict) -> Dict:
        severity = self._determine_severity(detection_result)
        alert = {
            "alert_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "severity": severity.value, "category": "prompt_injection",
            "title": f"Prompt Injection: {detection_result.get('max_threat_level', 'unknown')}",
            "description": self._format_description(detection_result),
            "detections": detection_result.get("detections", []),
            "context": {"session_id": context.get("session_id"), "user_id": context.get("user_id")},
            "action_taken": detection_result.get("action_required"),
            "recommendations": self._generate_recommendations(detection_result)
        }
        await self._route_alert(alert, severity)
        return alert
    
    def _determine_severity(self, detection_result: Dict) -> AlertSeverity:
        threat = detection_result.get("max_threat_level", "low")
        if threat in ("critical", "high"): return AlertSeverity.CRITICAL
        if threat == "medium": return AlertSeverity.WARNING
        return AlertSeverity.INFO
    
    def _format_description(self, detection_result: Dict) -> str:
        detections = detection_result.get("detections", [])
        lines = [f"Detected {len(detections)} injection pattern(s):", ""]
        for d in detections:
            lines.append(f"- {d['rule_name']} ({d['threat_level']}): {d['description']}")
        return "\n".join(lines)
    
    def _generate_recommendations(self, detection_result: Dict) -> List[str]:
        recs = []
        if detection_result.get("max_threat_level") == "critical":
            recs.extend([
                "Immediate: Review session logs for compromise",
                "Immediate: Consider session termination"
            ])
        if detection_result.get("action_required") == "lockdown":
            recs.append("System in lockdown - admin unlock required")
        recs.append("Review: Update detection rules if false positive")
        return recs
    
    async def _route_alert(self, alert: Dict, severity: AlertSeverity):
        for channel in self.channels:
            if channel.min_severity.value <= severity.value:
                await channel.send(alert)
```

---

## Appendix: Security Configuration Summary

### A.1 Environment Variables

```bash
# Security-critical (generate fresh per deployment)
export TALOS_HMAC_KEY="$(openssl rand -hex 32)"
export TALOS_STRIKE_KEY="$(openssl rand -hex 32)"
export TALOS_AUDIT_KEY="$(openssl rand -hex 32)"
export TALOS_TTS_SEED="$(openssl rand -hex 16)"

# Quarantine
export TALOS_QUARANTINE_MIN_DURATION_HOURS=24
export TALOS_QUARANTINE_MAX_EXECUTIONS=10

# Strike system
export TALOS_STRIKE_MAX=3
export TALOS_STRIKE_EXPIRY_DAYS=30

# Zombie reaper
export REAPER_TIMEOUT_MS=300000
export REAPER_CHECK_INTERVAL_MS=5000
export REAPER_FORCE_KILL_AFTER_MS=30000

# Socket proxy
export DOCKER_SOCKET_PROXY_RATE_LIMIT=100
```

### A.2 File Permissions

```bash
chmod 700 ~/talos/skills/quarantine
chmod 755 ~/talos/skills/active
chmod 700 ~/talos/skills/deprecated
chmod 700 ~/talos/skills/rollback
chmod 750 ~/talos/logs
chmod 600 /etc/talos/keys/*.key
```

---

*Document Version: 4.0*  
*Classification: Implementation Specification*  
*Security Level: Internal*
