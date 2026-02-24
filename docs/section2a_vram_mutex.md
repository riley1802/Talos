# SECTION 2 (Part A): Short-Term Operational Logic - VRAM Mutex & Context Management

## Talos v4.0 Master Implementation Specification

**Version:** 4.0.0  
**Date:** 2024  
**Classification:** Technical Implementation Specification  
**Component:** Core Runtime Operations

---

## Table of Contents

1. [2.1 VRAM Mutex State Machine](#21-vram-mutex-state-machine)
2. [2.2 Context Pruning Algorithm](#22-context-pruning-algorithm)
3. [2.3 RAG Logic Implementation](#23-rag-logic-implementation)
4. [2.4 Gemini Circuit Breaker](#24-gemini-circuit-breaker)

---

## 2.1 VRAM Mutex State Machine

### 2.1.1 Overview

The VRAM Mutex is a semaphore-based resource management system that ensures exclusive access to GPU memory for model swapping between Qwen Coder (Logic) and Qwen VL (Vision). The system implements hard timeouts and process kill procedures to prevent deadlocks.

### 2.1.2 State Definitions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VRAM MUTEX STATE DIAGRAM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌─────────┐    load_coder()    ┌──────────────┐                         │
│    │  IDLE   │ ─────────────────> │ LOADING_CODER│                         │
│    │  [00]   │ <───────────────── │    [10]      │                         │
│    └────┬────┘   load_complete    └──────┬───────┘                         │
│         │                                  │                                │
│         │ load_vl()                        │ unload_coder()                 │
│         ▼                                  ▼                                │
│    ┌─────────┐                      ┌──────────────┐                        │
│    │LOADING_ │                      │  UNLOADING   │                        │
│    │   VL    │                      │    [20]      │                        │
│    │  [01]   │ <────────────────────│              │                        │
│    └────┬────┘   load_vl()          └──────┬───────┘                        │
│         │                                  ▲                                │
│         │ unload_vl()                      │ unload_vl()                    │
│         └──────────────────────────────────┘                                │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────┐        │
│    │                         ERROR [FF]                           │        │
│    │  (Terminal state - requires manual intervention or restart)  │        │
│    └──────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1.3 State Enumeration

```python
class VRAMState(Enum):
    """
    VRAM Mutex State Enumeration
    
    State Encoding (hex):
    - IDLE [0x00]: No model loaded, VRAM available
    - LOADING_CODER [0x10]: Qwen Coder loading into VRAM
    - LOADING_VL [0x01]: Qwen VL loading into VRAM  
    - UNLOADING [0x20]: Model unloading from VRAM
    - ERROR [0xFF]: Fatal error state
    """
    IDLE = 0x00
    LOADING_CODER = 0x10
    LOADING_VL = 0x01
    UNLOADING = 0x20
    ERROR = 0xFF
```

### 2.1.4 State Transition Table

| Current State | Event | Next State | Timeout | Action |
|--------------|-------|------------|---------|--------|
| IDLE | load_coder() | LOADING_CODER | 30s | Acquire semaphore, start load |
| IDLE | load_vl() | LOADING_VL | 30s | Acquire semaphore, start load |
| LOADING_CODER | load_complete | IDLE | N/A | Release semaphore, ready |
| LOADING_CODER | load_timeout | UNLOADING | 30s | Trigger emergency unload |
| LOADING_CODER | load_error | ERROR | N/A | Log, enter error state |
| LOADING_VL | load_complete | IDLE | N/A | Release semaphore, ready |
| LOADING_VL | load_timeout | UNLOADING | 30s | Trigger emergency unload |
| LOADING_VL | load_error | ERROR | N/A | Log, enter error state |
| UNLOADING | unload_complete | IDLE | N/A | Clear semaphore, cleanup |
| UNLOADING | unload_timeout | ERROR | N/A | Kill process, cleanup |
| UNLOADING | nvidia_smi_error | ERROR | N/A | Kill process, cleanup |

### 2.1.5 State Transition Conditions

```
TRANSITION CONDITIONS (Boolean Logic):

T1: IDLE → LOADING_CODER
    Condition: semaphore.acquire(timeout=30s) AND model_path_valid AND vram_available > 7GB
    
T2: IDLE → LOADING_VL  
    Condition: semaphore.acquire(timeout=30s) AND model_path_valid AND vram_available > 9GB

T3: LOADING_CODER → IDLE
    Condition: model.load() completed AND model.verify() == True
    
T4: LOADING_CODER → UNLOADING
    Condition: elapsed_time > 30s OR load_exception != None
    
T5: LOADING_VL → IDLE
    Condition: model.load() completed AND model.verify() == True
    
T6: LOADING_VL → UNLOADING
    Condition: elapsed_time > 30s OR load_exception != None
    
T7: UNLOADING → IDLE
    Condition: model.unload() completed AND nvidia_smi.vram_used < 1GB
    
T8: UNLOADING → ERROR
    Condition: elapsed_time > 30s OR nvidia_smi_error OR kill_signal_failed
```

### 2.1.6 Timeout Handling Specification

```python
class VRAMTimeoutConfig:
    """
    Timeout Configuration Constants
    All timeouts in seconds
    """
    SEMAPHORE_ACQUIRE_TIMEOUT = 30.0    # Max wait for semaphore
    MODEL_LOAD_TIMEOUT = 30.0            # Max time for model load
    MODEL_UNLOAD_TIMEOUT = 30.0          # Max time for model unload
    NVIDIA_SMI_TIMEOUT = 5.0             # Max time for nvidia-smi query
    PROCESS_KILL_TIMEOUT = 10.0          # Max time for SIGTERM before SIGKILL
    RECOVERY_COOLDOWN = 60.0             # Cooldown after forced kill

class VRAMTimeoutHandler:
    """
    Timeout handling with escalation procedures
    """
    
    def __init__(self):
        self.timeout_deadline = None
        self.watchdog_thread = None
        self.kill_escalation_level = 0  # 0=none, 1=SIGTERM, 2=SIGKILL
        
    def start_timeout_watchdog(self, timeout_seconds: float, 
                                on_timeout: Callable,
                                escalation_proc: Callable):
        """
        Start watchdog timer with escalation procedure
        """
        self.timeout_deadline = time.monotonic() + timeout_seconds
        self.kill_escalation_level = 0
        
        def watchdog():
            while time.monotonic() < self.timeout_deadline:
                time.sleep(0.1)  # 100ms polling interval
                
                # Check for early completion signal
                if self._check_completion_signal():
                    return
                    
            # Timeout reached - execute callback
            on_timeout()
            
            # Start escalation timer
            escalation_deadline = time.monotonic() + VRAMTimeoutConfig.PROCESS_KILL_TIMEOUT
            while time.monotonic() < escalation_deadline:
                if self._check_completion_signal():
                    return
                time.sleep(0.1)
                
            # Escalation timeout - force kill
            escalation_proc()
            
        self.watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        self.watchdog_thread.start()
```

### 2.1.7 29-Second Unload Hang Handling

```python
class UnloadHangHandler:
    """
    Handles the critical case where unload hangs for 29 seconds
    This is the final warning before forced termination
    """
    
    UNLOAD_HANG_THRESHOLD = 29.0  # Seconds before emergency action
    
    async def handle_unload_hang(self, model_pid: int, model_type: str) -> UnloadResult:
        """
        EMERGENCY PROCEDURE: Unload has hung for 29 seconds
        
        Flow:
        1. Log critical error
        2. Attempt graceful SIGTERM
        3. Wait 1 second
        4. If still alive, SIGKILL
        5. Force VRAM cleanup via nvidia-smi --gpu-reset (if supported)
        6. Enter recovery cooldown
        """
        
        # CRITICAL LOG ENTRY
        self.logger.critical(
            f"VRAM_MUTEX_UNLOAD_HANG: "
            f"model={model_type}, "
            f"pid={model_pid}, "
            f"hang_duration=29s, "
            f"action=EMERGENCY_KILL"
        )
        
        # Phase 1: Attempt graceful termination
        kill_result = await self._attempt_graceful_kill(model_pid)
        
        if kill_result.success:
            return UnloadResult(
                status=UnloadStatus.GRACEFUL_RECOVERY,
                cleanup_performed=True,
                recovery_time_estimate=VRAMTimeoutConfig.RECOVERY_COOLDOWN
            )
        
        # Phase 2: Force kill
        force_kill_result = await self._force_kill(model_pid)
        
        if not force_kill_result.success:
            # Phase 3: Nuclear option - GPU reset
            gpu_reset_result = await self._attempt_gpu_reset()
            
            if not gpu_reset_result.success:
                # FATAL: Cannot recover
                return UnloadResult(
                    status=UnloadStatus.FATAL_ERROR,
                    requires_restart=True,
                    error_code=ErrorCode.GPU_UNRECOVERABLE
                )
        
        # Enter recovery cooldown
        await self._enter_recovery_cooldown()
        
        return UnloadResult(
            status=UnloadStatus.FORCED_RECOVERY,
            cleanup_performed=True,
            recovery_time_estimate=VRAMTimeoutConfig.RECOVERY_COOLDOWN
        )
    
    async def _attempt_graceful_kill(self, pid: int) -> KillResult:
        """
        Send SIGTERM and wait for process termination
        """
        try:
            os.kill(pid, signal.SIGTERM)
            
            # Wait up to 1 second for termination
            for _ in range(10):  # 10 x 100ms = 1 second
                if not self._process_exists(pid):
                    return KillResult(success=True, method=KillMethod.SIGTERM)
                await asyncio.sleep(0.1)
                
            return KillResult(success=False, method=KillMethod.SIGTERM)
            
        except ProcessLookupError:
            return KillResult(success=True, method=KillMethod.ALREADY_TERMINATED)
    
    async def _force_kill(self, pid: int) -> KillResult:
        """
        Send SIGKILL - process cannot ignore this
        """
        try:
            os.kill(pid, signal.SIGKILL)
            
            # Wait up to 2 seconds for kernel to reap process
            for _ in range(20):  # 20 x 100ms = 2 seconds
                if not self._process_exists(pid):
                    return KillResult(success=True, method=KillMethod.SIGKILL)
                await asyncio.sleep(0.1)
                
            return KillResult(success=False, method=KillMethod.SIGKILL)
            
        except ProcessLookupError:
            return KillResult(success=True, method=KillMethod.ALREADY_TERMINATED)
```

### 2.1.8 nvidia-smi Error Handling

```python
class NvidiaSMIErrorHandler:
    """
    Handles errors from nvidia-smi queries
    """
    
    class NvidiaSMIError(Enum):
        COMMAND_NOT_FOUND = "nvidia-smi executable not found"
        DRIVER_ERROR = "NVIDIA driver error"
        GPU_NOT_FOUND = "No GPU detected"
        TIMEOUT = "nvidia-smi query timeout"
        PARSE_ERROR = "Failed to parse nvidia-smi output"
        PERMISSION_DENIED = "Insufficient permissions"
    
    async def query_with_fallback(self, gpu_id: int = 0) -> GPUStatus:
        """
        Query GPU status with multiple fallback strategies
        """
        
        # Attempt 1: Standard nvidia-smi query
        try:
            return await self._query_nvidia_smi(gpu_id)
        except NvidiaSMIError.TIMEOUT:
            self.logger.warning("nvidia-smi timeout, attempting fallback")
        
        # Attempt 2: Query with reduced fields (faster)
        try:
            return await self._query_nvidia_smi_minimal(gpu_id)
        except Exception as e:
            self.logger.warning(f"Minimal query failed: {e}")
        
        # Attempt 3: Check if process exists via /proc
        try:
            return await self._query_via_procfs(gpu_id)
        except Exception as e:
            self.logger.warning(f"procfs query failed: {e}")
        
        # All attempts failed - return unknown status
        return GPUStatus(
            state=GPUState.UNKNOWN,
            vram_total_gb=0,
            vram_used_gb=0,
            error=NvidiaSMIError.DRIVER_ERROR,
            requires_manual_check=True
        )
    
    async def handle_critical_nvidia_error(self, error: NvidiaSMIError) -> ErrorAction:
        """
        Determine action based on nvidia-smi error type
        """
        ERROR_ACTION_MAP = {
            NvidiaSMIError.COMMAND_NOT_FOUND: ErrorAction(
                severity=Severity.CRITICAL,
                action=Action.ENTER_CPU_MODE,
                message="GPU monitoring unavailable - falling back to CPU"
            ),
            NvidiaSMIError.DRIVER_ERROR: ErrorAction(
                severity=Severity.CRITICAL,
                action=Action.RESTART_REQUIRED,
                message="NVIDIA driver error - system restart required"
            ),
            NvidiaSMIError.GPU_NOT_FOUND: ErrorAction(
                severity=Severity.CRITICAL,
                action=Action.ENTER_CPU_MODE,
                message="No GPU detected - falling back to CPU"
            ),
            NvidiaSMIError.TIMEOUT: ErrorAction(
                severity=Severity.HIGH,
                action=Action.RETRY_WITH_BACKOFF,
                message="nvidia-smi timeout - will retry with backoff"
            ),
            NvidiaSMIError.PARSE_ERROR: ErrorAction(
                severity=Severity.MEDIUM,
                action=Action.USE_LAST_KNOWN,
                message="Parse error - using last known GPU state"
            ),
            NvidiaSMIError.PERMISSION_DENIED: ErrorAction(
                severity=Severity.CRITICAL,
                action=Action.ESCALATE_PRIVILEGES,
                message="Permission denied - requires elevated privileges"
            )
        }
        
        return ERROR_ACTION_MAP.get(error, ErrorAction(
            severity=Severity.UNKNOWN,
            action=Action.LOG_AND_CONTINUE,
            message=f"Unknown nvidia-smi error: {error}"
        ))
```

### 2.1.9 Process Kill Procedure with Cleanup

```python
class ProcessKillProcedure:
    """
    Complete process kill procedure with comprehensive cleanup
    """
    
    async def execute_kill_procedure(self, target: ModelProcess) -> KillReport:
        """
        EXECUTE KILL PROCEDURE
        
        Phase 1: Pre-kill Preparation
        Phase 2: Signal Escalation
        Phase 3: Post-kill Verification
        Phase 4: Resource Cleanup
        Phase 5: State Recovery
        """
        
        report = KillReport(target_pid=target.pid, start_time=time.monotonic())
        
        # === PHASE 1: PRE-KILL PREPARATION ===
        self.logger.info(f"KILL_PROCEDURE_START: pid={target.pid}, model={target.model_type}")
        
        # Capture pre-kill state
        pre_kill_state = await self._capture_system_state()
        report.pre_kill_state = pre_kill_state
        
        # Notify dependent services
        await self._notify_service_shutdown(target.model_type)
        
        # Flush any pending I/O
        await self._flush_model_io(target)
        
        # === PHASE 2: SIGNAL ESCALATION ===
        
        # Step 2.1: SIGTERM (graceful)
        self.logger.info(f"KILL_SIGTERM: pid={target.pid}")
        try:
            os.kill(target.pid, signal.SIGTERM)
            await asyncio.sleep(0.5)
            
            if not self._process_exists(target.pid):
                report.termination_method = KillMethod.SIGTERM
                report.termination_time = time.monotonic()
                
        except ProcessLookupError:
            report.termination_method = KillMethod.ALREADY_TERMINATED
            report.termination_time = time.monotonic()
            
        # Step 2.2: SIGKILL if still alive
        if self._process_exists(target.pid):
            self.logger.warning(f"KILL_SIGKILL: pid={target.pid}")
            try:
                os.kill(target.pid, signal.SIGKILL)
                await asyncio.sleep(1.0)
                
                if not self._process_exists(target.pid):
                    report.termination_method = KillMethod.SIGKILL
                    report.termination_time = time.monotonic()
                    
            except ProcessLookupError:
                report.termination_method = KillMethod.ALREADY_TERMINATED
                report.termination_time = time.monotonic()
        
        # Step 2.3: Zombie process check
        if self._is_zombie(target.pid):
            self.logger.error(f"KILL_ZOMBIE_DETECTED: pid={target.pid}")
            await self._handle_zombie_process(target.pid)
            report.zombie_detected = True
        
        # === PHASE 3: POST-KILL VERIFICATION ===
        
        # Verify process is truly gone
        for attempt in range(5):
            if not self._process_exists(target.pid):
                break
            self.logger.warning(f"KILL_PROCESS_STILL_ALIVE: attempt={attempt}, pid={target.pid}")
            await asyncio.sleep(0.5)
        
        if self._process_exists(target.pid):
            report.verification_status = VerificationStatus.FAILED
            report.requires_manual_intervention = True
            return report
        
        report.verification_status = VerificationStatus.PASSED
        
        # === PHASE 4: RESOURCE CLEANUP ===
        
        # Clear CUDA cache
        await self._clear_cuda_cache()
        
        # Release VRAM allocations
        freed_vram = await self._force_vram_release()
        report.vram_freed_gb = freed_vram
        
        # Clean up shared memory segments
        shm_cleaned = await self._cleanup_shared_memory(target.model_type)
        report.shm_segments_cleaned = shm_cleaned
        
        # Remove temporary files
        files_removed = await self._cleanup_temp_files(target.model_type)
        report.temp_files_removed = files_removed
        
        # === PHASE 5: STATE RECOVERY ===
        
        # Reset mutex state
        await self._reset_mutex_state()
        
        # Clear semaphore
        await self._clear_semaphore()
        
        # Update system state
        post_kill_state = await self._capture_system_state()
        report.post_kill_state = post_kill_state
        
        # Enter recovery cooldown
        await self._enter_recovery_cooldown(VRAMTimeoutConfig.RECOVERY_COOLDOWN)
        
        report.completion_time = time.monotonic()
        report.total_duration = report.completion_time - report.start_time
        
        self.logger.info(
            f"KILL_PROCEDURE_COMPLETE: "
            f"duration={report.total_duration:.2f}s, "
            f"method={report.termination_method}, "
            f"vram_freed={report.vram_freed_gb:.2f}GB"
        )
        
        return report
    
    async def _clear_cuda_cache(self):
        """
        Force clear PyTorch/TensorFlow CUDA cache
        """
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            
        import gc
        gc.collect()
```

### 2.1.10 Recovery Logic After Forced Kill

```python
class PostKillRecovery:
    """
    Recovery procedures after a forced process kill
    """
    
    RECOVERY_STATES = ['COOLDOWN', 'DIAGNOSTIC', 'VALIDATION', 'RESTORE', 'READY']
    
    async def execute_recovery(self, kill_report: KillReport) -> RecoveryResult:
        """
        RECOVERY PROCEDURE AFTER FORCED KILL
        
        State Machine:
        COOLDOWN -> DIAGNOSTIC -> VALIDATION -> RESTORE -> READY
        """
        
        recovery_state = RecoveryState()
        
        # === STATE: COOLDOWN ===
        recovery_state.current = 'COOLDOWN'
        self.logger.info("RECOVERY_STATE: COOLDOWN")
        
        await self._cooldown_phase(VRAMTimeoutConfig.RECOVERY_COOLDOWN)
        
        # === STATE: DIAGNOSTIC ===
        recovery_state.current = 'DIAGNOSTIC'
        self.logger.info("RECOVERY_STATE: DIAGNOSTIC")
        
        diagnostic_result = await self._run_diagnostics()
        
        if diagnostic_result.critical_issues:
            return RecoveryResult(
                success=False,
                state='DIAGNOSTIC_FAILED',
                issues=diagnostic_result.critical_issues,
                requires_restart=True
            )
        
        # === STATE: VALIDATION ===
        recovery_state.current = 'VALIDATION'
        self.logger.info("RECOVERY_STATE: VALIDATION")
        
        validation_result = await self._validate_system_state()
        
        if not validation_result.gpu_accessible:
            return RecoveryResult(
                success=False,
                state='VALIDATION_FAILED',
                error="GPU not accessible post-kill",
                fallback_action=FallbackAction.CPU_MODE
            )
        
        if validation_result.vram_fragmentation > 0.5:
            await self._defragment_vram()
        
        # === STATE: RESTORE ===
        recovery_state.current = 'RESTORE'
        self.logger.info("RECOVERY_STATE: RESTORE")
        
        # Restore mutex to clean state
        await self._restore_mutex_state()
        
        # Clear any stale locks
        await self._clear_stale_locks()
        
        # Restore default model (if configured)
        if self.config.auto_restore_default_model:
            restore_result = await self._load_default_model()
            if not restore_result.success:
                self.logger.warning("Default model restore failed, staying in IDLE")
        
        # === STATE: READY ===
        recovery_state.current = 'READY'
        self.logger.info("RECOVERY_STATE: READY")
        
        return RecoveryResult(
            success=True,
            state='READY',
            recovery_duration=recovery_state.total_duration,
            system_state=await self._capture_system_state()
        )
    
    async def _cooldown_phase(self, duration_seconds: float):
        """
        Cooldown period to let system stabilize
        """
        self.logger.info(f"RECOVERY_COOLDOWN_START: duration={duration_seconds}s")
        
        start_time = time.monotonic()
        check_interval = 1.0  # Check every second
        
        while time.monotonic() - start_time < duration_seconds:
            elapsed = time.monotonic() - start_time
            remaining = duration_seconds - elapsed
            
            # Log progress every 10 seconds
            if int(elapsed) % 10 == 0:
                self.logger.info(f"RECOVERY_COOLDOWN: elapsed={elapsed:.0f}s, remaining={remaining:.0f}s")
            
            # Check for early termination signal
            if self._check_early_recovery_signal():
                self.logger.info("RECOVERY_COOLDOWN: Early termination requested")
                break
            
            await asyncio.sleep(check_interval)
        
        self.logger.info("RECOVERY_COOLDOWN_COMPLETE")
    
    async def _run_diagnostics(self) -> DiagnosticResult:
        """
        Run comprehensive system diagnostics
        """
        diagnostics = DiagnosticResult()
        
        # Check 1: GPU accessibility
        try:
            gpu_info = await self._query_gpu_status()
            diagnostics.gpu_accessible = gpu_info.accessible
            diagnostics.vram_available = gpu_info.vram_free
        except Exception as e:
            diagnostics.critical_issues.append(f"GPU diagnostic failed: {e}")
        
        # Check 2: Process cleanup verification
        zombie_processes = await self._find_zombie_processes()
        if zombie_processes:
            diagnostics.warnings.append(f"Found {len(zombie_processes)} zombie processes")
        
        # Check 3: Shared memory cleanup
        orphaned_shm = await self._find_orphaned_shm()
        if orphaned_shm:
            diagnostics.warnings.append(f"Found {len(orphaned_shm)} orphaned SHM segments")
        
        # Check 4: File descriptor leaks
        fd_count = await self._count_open_fds()
        if fd_count > self.config.fd_threshold:
            diagnostics.warnings.append(f"High file descriptor count: {fd_count}")
        
        # Check 5: Mutex state consistency
        mutex_state = await self._check_mutex_consistency()
        if not mutex_state.consistent:
            diagnostics.critical_issues.append(f"Mutex inconsistency: {mutex_state.issues}")
        
        return diagnostics
```

---

## 2.2 Context Pruning Algorithm

### 2.2.1 Overview

The Context Pruning Algorithm manages the strictly capped ChromaDB vector store (100,000 vectors maximum). It uses a hybrid scoring system combining frequency-based access patterns with age-based decay to determine which vectors to retain during compaction.

### 2.2.2 Vector Scoring System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      VECTOR RETENTION SCORE FORMULA                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Score(v) = (W_freq × FrequencyScore(v)) +                                │
│              (W_age × AgeScore(v)) +                                        │
│              (W_priority × PriorityScore(v)) +                              │
│              (W_recency × RecencyScore(v))                                  │
│                                                                             │
│   Where:                                                                    │
│   - W_freq = 0.30 (frequency weight)                                        │
│   - W_age = 0.25 (age weight)                                               │
│   - W_priority = 0.35 (priority weight - HIGHEST)                           │
│   - W_recency = 0.10 (recency weight)                                       │
│                                                                             │
│   All weights sum to 1.0                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2.3 Component Score Formulas

```python
class VectorScoringEngine:
    """
    Hybrid scoring engine for vector retention decisions
    """
    
    # Weight constants
    W_FREQUENCY = 0.30
    W_AGE = 0.25
    W_PRIORITY = 0.35
    W_RECENCY = 0.10
    
    # Age decay parameters
    AGE_DECAY_HALF_LIFE_DAYS = 30  # Half-life for age score
    AGE_DECAY_LAMBDA = math.log(2) / (AGE_DECAY_HALF_LIFE_DAYS * 24 * 3600)
    
    # Frequency normalization
    MAX_FREQUENCY_CAP = 1000  # Cap frequency count at 1000
    
    def calculate_frequency_score(self, access_count: int, 
                                   time_window_hours: float = 168) -> float:
        """
        FREQUENCY SCORE: Normalized access frequency
        
        Formula: score = min(access_count, MAX_CAP) / MAX_CAP
        
        Higher frequency = higher score
        """
        capped_count = min(access_count, self.MAX_FREQUENCY_CAP)
        return capped_count / self.MAX_FREQUENCY_CAP
    
    def calculate_age_score(self, created_timestamp: float,
                            current_timestamp: float) -> float:
        """
        AGE SCORE: Exponential decay based on age
        
        Formula: score = exp(-λ × age_seconds)
        
        - Newer vectors have higher scores
        - Decay follows exponential curve with 30-day half-life
        - Score approaches 0 but never reaches it
        """
        age_seconds = current_timestamp - created_timestamp
        
        if age_seconds < 0:
            # Future-dated vector (clock skew) - treat as new
            return 1.0
        
        score = math.exp(-self.AGE_DECAY_LAMBDA * age_seconds)
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]
    
    def calculate_priority_score(self, priority_tag: str) -> float:
        """
        PRIORITY SCORE: Tag-based priority multiplier
        
        Priority Tags:
        - 'permanent': 1.0 (never delete)
        - 'high': 0.9
        - 'session': 0.5
        - 'temporary': 0.1
        - default: 0.5
        """
        PRIORITY_MAP = {
            'permanent': 1.0,    # Never auto-delete
            'high': 0.9,         # Strongly prefer retention
            'session': 0.5,      # Normal retention
            'temporary': 0.1,    # Strongly prefer deletion
            'auto': 0.5          # Default
        }
        
        return PRIORITY_MAP.get(priority_tag, 0.5)
    
    def calculate_recency_score(self, last_access_timestamp: float,
                                 current_timestamp: float) -> float:
        """
        RECENCY SCORE: Time since last access
        
        Formula: score = 1 / (1 + log(1 + hours_since_access))
        
        - Recently accessed vectors get higher scores
        - Logarithmic decay prevents extreme differences
        """
        hours_since_access = (current_timestamp - last_access_timestamp) / 3600
        
        if hours_since_access < 0:
            return 1.0  # Future access (clock skew)
        
        score = 1.0 / (1.0 + math.log1p(hours_since_access))
        return max(0.0, min(1.0, score))
    
    def calculate_total_score(self, vector_metadata: VectorMetadata,
                               current_timestamp: float) -> float:
        """
        TOTAL RETENTION SCORE: Weighted combination of all factors
        """
        freq_score = self.calculate_frequency_score(
            vector_metadata.access_count
        )
        
        age_score = self.calculate_age_score(
            vector_metadata.created_at,
            current_timestamp
        )
        
        priority_score = self.calculate_priority_score(
            vector_metadata.priority_tag
        )
        
        recency_score = self.calculate_recency_score(
            vector_metadata.last_accessed_at,
            current_timestamp
        )
        
        total_score = (
            self.W_FREQUENCY * freq_score +
            self.W_AGE * age_score +
            self.W_PRIORITY * priority_score +
            self.W_RECENCY * recency_score
        )
        
        return total_score
```

### 2.2.4 Priority Tag System

```python
class PriorityTagSystem:
    """
    Priority tag definitions and behavior
    """
    
    class PriorityLevel(Enum):
        """
        Priority levels with retention guarantees
        """
        PERMANENT = ('permanent', 1.0, None)      # Never auto-delete
        HIGH = ('high', 0.9, 365)                  # Retain 1 year minimum
        SESSION = ('session', 0.5, 30)             # Retain 30 days minimum
        TEMPORARY = ('temporary', 0.1, 1)          # Retain 1 day minimum
        AUTO = ('auto', 0.5, 7)                    # Default: 7 days
    
    def get_retention_guarantee(self, tag: str) -> Optional[int]:
        """
        Get minimum retention period in days for a tag
        Returns None for permanent (infinite)
        """
        GUARANTEE_MAP = {
            'permanent': None,      # Infinite
            'high': 365,            # 1 year
            'session': 30,          # 30 days
            'temporary': 1,         # 1 day
            'auto': 7               # 7 days
        }
        return GUARANTEE_MAP.get(tag, 7)
    
    def can_auto_delete(self, tag: str, age_days: int) -> bool:
        """
        Check if a vector can be auto-deleted based on tag and age
        """
        guarantee = self.get_retention_guarantee(tag)
        
        if guarantee is None:
            return False  # Permanent - never delete
        
        return age_days >= guarantee
```

### 2.2.5 Batch Pruning Implementation

```python
class BatchPruningEngine:
    """
    Batch pruning with atomicity guarantees
    """
    
    # Configuration
    CHROMADB_MAX_VECTORS = 100_000
    COMPACTION_THRESHOLD = 0.90  # Trigger at 90% capacity
    DELETE_BATCH_SIZE = 1000     # Delete in batches for performance
    PRUNE_TARGET_RATIO = 0.10    # Delete 10% of vectors when compacting
    
    # Atomicity settings
    ATOMIC_BATCH_SIZE = 100      # Atomic transaction batch size
    MAX_RETRY_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = 1.0
    
    async def prune_if_needed(self, chroma_collection) -> PruningResult:
        """
        Check if pruning is needed and execute if so
        
        Trigger Condition: vector_count > (MAX_VECTORS × COMPACTION_THRESHOLD)
        """
        
        # Get current count
        current_count = await self._get_vector_count(chroma_collection)
        threshold_count = int(self.CHROMADB_MAX_VECTORS * self.COMPACTION_THRESHOLD)
        
        if current_count <= threshold_count:
            return PruningResult(
                action=PruningAction.NONE,
                vectors_deleted=0,
                reason=f"Count {current_count} below threshold {threshold_count}"
            )
        
        # Calculate target count after pruning
        target_count = int(self.CHROMADB_MAX_VECTORS * (1 - self.PRUNE_TARGET_RATIO))
        vectors_to_delete = current_count - target_count
        
        self.logger.info(
            f"PRUNE_TRIGGERED: current={current_count}, "
            f"target={target_count}, delete={vectors_to_delete}"
        )
        
        # Execute pruning
        return await self._execute_pruning(
            chroma_collection,
            vectors_to_delete
        )
    
    async def _execute_pruning(self, chroma_collection, 
                                vectors_to_delete: int) -> PruningResult:
        """
        EXECUTE BATCH PRUNING WITH ATOMICITY
        
        Algorithm:
        1. Score all vectors
        2. Sort by score (ascending - lowest scores first)
        3. Filter out protected vectors (permanent tag, within guarantee period)
        4. Delete in atomic batches
        5. Verify deletion count
        6. Rollback on failure
        """
        
        start_time = time.monotonic()
        current_timestamp = time.time()
        
        # Step 1: Fetch all vectors with metadata
        all_vectors = await self._fetch_all_vectors(chroma_collection)
        
        # Step 2: Score all vectors
        scored_vectors = []
        for vector in all_vectors:
            score = self.scoring_engine.calculate_total_score(
                vector.metadata,
                current_timestamp
            )
            scored_vectors.append((vector.id, score, vector.metadata))
        
        # Step 3: Sort by score (lowest first - candidates for deletion)
        scored_vectors.sort(key=lambda x: x[1])
        
        # Step 4: Filter protected vectors
        deletable_ids = []
        for vid, score, metadata in scored_vectors:
            if self._is_vector_protected(metadata, current_timestamp):
                continue
            deletable_ids.append(vid)
            
            if len(deletable_ids) >= vectors_to_delete:
                break
        
        if len(deletable_ids) < vectors_to_delete:
            self.logger.warning(
                f"PRUNE_INSUFFICIENT_DELETABLE: "
                f"requested={vectors_to_delete}, available={len(deletable_ids)}"
            )
        
        # Step 5: Delete in atomic batches
        deleted_count = 0
        failed_batches = []
        
        for batch_start in range(0, len(deletable_ids), self.ATOMIC_BATCH_SIZE):
            batch_end = min(batch_start + self.ATOMIC_BATCH_SIZE, len(deletable_ids))
            batch_ids = deletable_ids[batch_start:batch_end]
            
            batch_success = await self._delete_batch_atomic(
                chroma_collection,
                batch_ids
            )
            
            if batch_success:
                deleted_count += len(batch_ids)
            else:
                failed_batches.append((batch_start, batch_end))
                self.logger.error(f"PRUNE_BATCH_FAILED: batch={batch_start}-{batch_end}")
        
        # Step 6: Retry failed batches
        for batch_start, batch_end in failed_batches:
            batch_ids = deletable_ids[batch_start:batch_end]
            
            for attempt in range(self.MAX_RETRY_ATTEMPTS):
                await asyncio.sleep(self.RETRY_BACKOFF_SECONDS * (2 ** attempt))
                
                batch_success = await self._delete_batch_atomic(
                    chroma_collection,
                    batch_ids
                )
                
                if batch_success:
                    deleted_count += len(batch_ids)
                    break
                
                self.logger.warning(
                    f"PRUNE_RETRY_FAILED: attempt={attempt+1}, batch={batch_start}-{batch_end}"
                )
        
        duration = time.monotonic() - start_time
        
        return PruningResult(
            action=PruningAction.EXECUTED,
            vectors_deleted=deleted_count,
            vectors_requested=vectors_to_delete,
            duration_seconds=duration,
            failed_batches=len(failed_batches)
        )
    
    def _is_vector_protected(self, metadata: VectorMetadata, 
                              current_timestamp: float) -> bool:
        """
        Check if a vector is protected from deletion
        """
        # Permanent tag = never delete
        if metadata.priority_tag == 'permanent':
            return True
        
        # Check retention guarantee
        age_seconds = current_timestamp - metadata.created_at
        age_days = age_seconds / (24 * 3600)
        
        guarantee_days = self.priority_system.get_retention_guarantee(
            metadata.priority_tag
        )
        
        if guarantee_days is not None and age_days < guarantee_days:
            return True
        
        return False
    
    async def _delete_batch_atomic(self, chroma_collection, 
                                    vector_ids: List[str]) -> bool:
        """
        Atomic batch deletion with transaction semantics
        
        Atomicity Guarantee: Either all vectors in batch are deleted,
        or none are (on failure, collection remains unchanged)
        """
        try:
            # ChromaDB delete is inherently atomic per call
            chroma_collection.delete(ids=vector_ids)
            
            # Verify deletion
            verify_result = await self._verify_deletion(chroma_collection, vector_ids)
            
            if not verify_result.success:
                self.logger.error(f"PRUNE_VERIFY_FAILED: {verify_result.missing_ids}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"PRUNE_BATCH_EXCEPTION: {e}")
            return False
    
    async def _verify_deletion(self, chroma_collection, 
                                deleted_ids: List[str]) -> VerificationResult:
        """
        Verify that vectors were actually deleted
        """
        try:
            # Query for the deleted IDs
            result = chroma_collection.get(ids=deleted_ids)
            
            if result and result.get('ids'):
                # Some IDs still exist
                return VerificationResult(
                    success=False,
                    missing_ids=result['ids']
                )
            
            return VerificationResult(success=True)
            
        except Exception as e:
            self.logger.error(f"PRUNE_VERIFY_EXCEPTION: {e}")
            return VerificationResult(success=False, error=str(e))
```

### 2.2.6 Compaction Cron Implementation

```python
class CompactionCron:
    """
    Scheduled compaction job for ChromaDB
    Runs daily at 4:00 AM (during Nocturnal Context Consolidation)
    """
    
    SCHEDULE_HOUR = 4
    SCHEDULE_MINUTE = 0
    
    async def run_compaction(self, chroma_collection) -> CompactionResult:
        """
        COMPACTION CRON JOB
        
        Executes during Nocturnal Context Consolidation:
        1. Check vector count
        2. If > 90% capacity, delete oldest 10%
        3. Also delete temporary vectors older than 30 days
        """
        
        self.logger.info("COMPACTION_CRON_START")
        
        current_timestamp = time.time()
        results = []
        
        # Task 1: Capacity-based pruning
        prune_result = await self.pruning_engine.prune_if_needed(chroma_collection)
        results.append(prune_result)
        
        # Task 2: Age-based cleanup for temporary vectors
        age_cleanup_result = await self._cleanup_old_temporary_vectors(
            chroma_collection,
            current_timestamp
        )
        results.append(age_cleanup_result)
        
        # Task 3: Orphaned vector cleanup
        orphan_result = await self._cleanup_orphaned_vectors(chroma_collection)
        results.append(orphan_result)
        
        total_deleted = sum(r.vectors_deleted for r in results)
        
        self.logger.info(f"COMPACTION_CRON_COMPLETE: total_deleted={total_deleted}")
        
        return CompactionResult(
            tasks=results,
            total_vectors_deleted=total_deleted,
            timestamp=current_timestamp
        )
    
    async def _cleanup_old_temporary_vectors(self, chroma_collection,
                                              current_timestamp: float) -> CleanupResult:
        """
        Delete temporary vectors older than 30 days
        """
        THIRTY_DAYS_SECONDS = 30 * 24 * 3600
        cutoff_timestamp = current_timestamp - THIRTY_DAYS_SECONDS
        
        # Query for old temporary vectors
        old_temp_vectors = chroma_collection.get(
            where={
                "$and": [
                    {"priority_tag": {"$eq": "temporary"}},
                    {"created_at": {"$lt": cutoff_timestamp}}
                ]
            }
        )
        
        if not old_temp_vectors or not old_temp_vectors.get('ids'):
            return CleanupResult(vectors_deleted=0, reason="No old temporary vectors")
        
        ids_to_delete = old_temp_vectors['ids']
        
        # Delete in batches
        deleted_count = 0
        for i in range(0, len(ids_to_delete), self.pruning_engine.DELETE_BATCH_SIZE):
            batch = ids_to_delete[i:i + self.pruning_engine.DELETE_BATCH_SIZE]
            chroma_collection.delete(ids=batch)
            deleted_count += len(batch)
        
        return CleanupResult(
            vectors_deleted=deleted_count,
            reason=f"Deleted temporary vectors older than 30 days"
        )
```

---

## 2.3 RAG Logic Implementation

### 2.3.1 Overview

The RAG (Retrieval Augmented Generation) system manages vector search, context window assembly, and relevance scoring to provide the most pertinent information to the language model within token constraints.

### 2.3.2 Vector Search Algorithm

```python
class VectorSearchEngine:
    """
    Multi-stage vector search with relevance scoring
    """
    
    # Search parameters
    DEFAULT_TOP_K = 10
    MAX_TOP_K = 50
    SIMILARITY_THRESHOLD = 0.7
    DIVERSITY_LAMBDA = 0.5  # MMR diversity parameter
    
    async def search(self, query: str, 
                     collection,
                     top_k: int = DEFAULT_TOP_K,
                     filters: Optional[Dict] = None) -> SearchResult:
        """
        MULTI-STAGE VECTOR SEARCH
        
        Stage 1: Initial similarity search
        Stage 2: Re-ranking with MMR (Maximal Marginal Relevance)
        Stage 3: Diversity filtering
        Stage 4: Final relevance scoring
        """
        
        # Stage 1: Generate query embedding
        query_embedding = await self._embed_query(query)
        
        # Stage 2: Initial retrieval (get more than needed for re-ranking)
        initial_k = min(top_k * 3, self.MAX_TOP_K)
        
        initial_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=initial_k,
            where=filters,
            include=["metadatas", "documents", "distances"]
        )
        
        if not initial_results['ids'][0]:
            return SearchResult(results=[], total_found=0)
        
        # Stage 3: MMR Re-ranking for diversity
        mmr_results = self._mmr_rerank(
            query_embedding,
            initial_results,
            top_k=top_k,
            lambda_param=self.DIVERSITY_LAMBDA
        )
        
        # Stage 4: Final relevance scoring
        scored_results = self._score_results(mmr_results, query)
        
        # Filter by similarity threshold
        filtered_results = [
            r for r in scored_results 
            if r.similarity_score >= self.SIMILARITY_THRESHOLD
        ]
        
        return SearchResult(
            results=filtered_results,
            total_found=len(initial_results['ids'][0]),
            returned=len(filtered_results)
        )
    
    def _mmr_rerank(self, query_embedding: List[float],
                    initial_results: Dict,
                    top_k: int,
                    lambda_param: float) -> List[SearchResultItem]:
        """
        Maximal Marginal Relevance Re-ranking
        
        MMR Formula:
        MMR = λ × Sim(query, doc) - (1-λ) × max(Sim(doc, selected_docs))
        
        Balances relevance vs diversity
        """
        
        candidates = []
        for i, doc_id in enumerate(initial_results['ids'][0]):
            candidates.append(SearchCandidate(
                id=doc_id,
                document=initial_results['documents'][0][i],
                metadata=initial_results['metadatas'][0][i],
                embedding=initial_results['embeddings'][0][i] if 'embeddings' in initial_results else None,
                similarity=1 - initial_results['distances'][0][i]  # Convert distance to similarity
            ))
        
        selected = []
        remaining = candidates.copy()
        
        while len(selected) < top_k and remaining:
            if not selected:
                # First selection: highest similarity
                best = max(remaining, key=lambda x: x.similarity)
            else:
                # MMR scoring
                best_mmr_score = -float('inf')
                best = None
                
                for candidate in remaining:
                    # Relevance component
                    relevance = candidate.similarity
                    
                    # Diversity component (max similarity to already selected)
                    max_sim_to_selected = max(
                        self._cosine_similarity(candidate.embedding, s.embedding)
                        for s in selected
                    ) if selected else 0
                    
                    # MMR score
                    mmr_score = (
                        lambda_param * relevance -
                        (1 - lambda_param) * max_sim_to_selected
                    )
                    
                    if mmr_score > best_mmr_score:
                        best_mmr_score = mmr_score
                        best = candidate
            
            selected.append(best)
            remaining.remove(best)
        
        return selected
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
```

### 2.3.3 Context Window Management

```python
class ContextWindowManager:
    """
    Manages assembly of retrieved context within token budget
    """
    
    # Token budgets (configurable)
    DEFAULT_MAX_CONTEXT_TOKENS = 4000
    RESERVED_RESPONSE_TOKENS = 1000
    SYSTEM_PROMPT_TOKENS = 500
    
    # Token estimation (rough approximation)
    TOKENS_PER_CHAR = 0.25  # ~4 chars per token for English
    
    def __init__(self, max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS):
        self.max_context_tokens = max_context_tokens
        self.available_tokens = (
            max_context_tokens - 
            self.RESERVED_RESPONSE_TOKENS - 
            self.SYSTEM_PROMPT_TOKENS
        )
    
    async def assemble_context(self, search_results: List[SearchResultItem],
                                query: str) -> AssembledContext:
        """
        ASSEMBLE CONTEXT WINDOW FROM SEARCH RESULTS
        
        Strategy:
        1. Sort by relevance score
        2. Add documents until token budget exhausted
        3. Prioritize documents that answer the query
        4. Include metadata for provenance
        """
        
        # Sort by relevance (highest first)
        sorted_results = sorted(
            search_results,
            key=lambda x: x.relevance_score,
            reverse=True
        )
        
        assembled_documents = []
        current_token_count = 0
        
        for result in sorted_results:
            # Estimate token count for this document
            doc_tokens = self._estimate_tokens(result.document)
            metadata_tokens = self._estimate_tokens(str(result.metadata))
            total_doc_tokens = doc_tokens + metadata_tokens + 10  # Buffer
            
            # Check if adding this document would exceed budget
            if current_token_count + total_doc_tokens > self.available_tokens:
                # Try to truncate document to fit
                remaining_tokens = self.available_tokens - current_token_count
                
                if remaining_tokens > 100:  # Minimum meaningful chunk
                    truncated_doc = self._truncate_to_tokens(
                        result.document,
                        remaining_tokens - metadata_tokens - 10
                    )
                    
                    assembled_documents.append(ContextDocument(
                        content=truncated_doc,
                        metadata=result.metadata,
                        truncated=True,
                        relevance_score=result.relevance_score
                    ))
                
                break
            
            # Add full document
            assembled_documents.append(ContextDocument(
                content=result.document,
                metadata=result.metadata,
                truncated=False,
                relevance_score=result.relevance_score
            ))
            
            current_token_count += total_doc_tokens
        
        return AssembledContext(
            documents=assembled_documents,
            total_tokens=current_token_count,
            documents_included=len(assembled_documents),
            documents_excluded=len(sorted_results) - len(assembled_documents)
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation"""
        return int(len(text) * self.TOKENS_PER_CHAR)
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget"""
        max_chars = int(max_tokens / self.TOKENS_PER_CHAR)
        
        if len(text) <= max_chars:
            return text
        
        # Try to truncate at sentence boundary
        truncated = text[:max_chars]
        last_sentence_end = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?')
        )
        
        if last_sentence_end > max_chars * 0.7:  # At least 70% of target
            return truncated[:last_sentence_end + 1]
        
        # Fallback: truncate at word boundary
        last_space = truncated.rfind(' ')
        if last_space > 0:
            return truncated[:last_space] + "..."
        
        return truncated + "..."
```

### 2.3.4 Relevance Scoring

```python
class RelevanceScorer:
    """
    Multi-factor relevance scoring for retrieved documents
    """
    
    # Scoring weights
    W_VECTOR_SIMILARITY = 0.40
    W_KEYWORD_MATCH = 0.25
    W_METADATA_RELEVANCE = 0.20
    W_RECENCY = 0.15
    
    def calculate_relevance(self, document: str,
                            metadata: Dict,
                            query: str,
                            vector_similarity: float,
                            current_timestamp: float) -> float:
        """
        COMPREHENSIVE RELEVANCE SCORE
        
        Combines:
        - Vector similarity (semantic match)
        - Keyword overlap (lexical match)
        - Metadata relevance (source quality)
        - Recency (temporal relevance)
        """
        
        # Component 1: Vector similarity (already computed)
        similarity_score = vector_similarity
        
        # Component 2: Keyword match score
        keyword_score = self._calculate_keyword_score(query, document)
        
        # Component 3: Metadata relevance
        metadata_score = self._calculate_metadata_score(metadata, query)
        
        # Component 4: Recency score
        recency_score = self._calculate_recency_score(metadata, current_timestamp)
        
        # Weighted combination
        total_score = (
            self.W_VECTOR_SIMILARITY * similarity_score +
            self.W_KEYWORD_MATCH * keyword_score +
            self.W_METADATA_RELEVANCE * metadata_score +
            self.W_RECENCY * recency_score
        )
        
        return min(1.0, max(0.0, total_score))  # Clamp to [0, 1]
    
    def _calculate_keyword_score(self, query: str, document: str) -> float:
        """
        Calculate keyword overlap score
        """
        query_terms = set(self._tokenize(query.lower()))
        doc_terms = set(self._tokenize(document.lower()))
        
        if not query_terms:
            return 0.0
        
        # Jaccard similarity
        intersection = len(query_terms & doc_terms)
        union = len(query_terms | doc_terms)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _calculate_metadata_score(self, metadata: Dict, query: str) -> float:
        """
        Score based on metadata quality and relevance
        """
        score = 0.0
        
        # Source quality
        source_quality = metadata.get('source_quality', 0.5)
        score += source_quality * 0.4
        
        # Query type match
        query_type = self._classify_query_type(query)
        doc_type = metadata.get('document_type', 'general')
        
        type_match_score = self._calculate_type_match(query_type, doc_type)
        score += type_match_score * 0.3
        
        # Verification status
        if metadata.get('verified', False):
            score += 0.2
        
        # User feedback (if available)
        feedback_score = metadata.get('user_feedback_score', 0.5)
        score += feedback_score * 0.1
        
        return min(1.0, score)
    
    def _calculate_recency_score(self, metadata: Dict, 
                                  current_timestamp: float) -> float:
        """
        Calculate recency score with exponential decay
        """
        created_at = metadata.get('created_at', 0)
        
        if created_at == 0:
            return 0.5  # Unknown age
        
        age_seconds = current_timestamp - created_at
        age_days = age_seconds / (24 * 3600)
        
        # Exponential decay with 90-day half-life
        half_life_days = 90
        decay_lambda = math.log(2) / half_life_days
        
        score = math.exp(-decay_lambda * age_days)
        return max(0.0, min(1.0, score))
```

### 2.3.5 Fallback Behavior at Capacity

```python
class CapacityFallbackHandler:
    """
    Fallback behaviors when ChromaDB is at capacity
    """
    
    async def handle_at_capacity(self, query: str,
                                  chroma_collection) -> FallbackResult:
        """
        FALLBACK BEHAVIOR WHEN CHROMADB AT CAPACITY
        
        Escalation Chain:
        1. Try aggressive pruning
        2. If still full, use Redis short-term cache
        3. If Redis unavailable, use keyword-only search
        4. If all fail, return empty context with warning
        """
        
        self.logger.warning("CHROMADB_AT_CAPACITY: Initiating fallback chain")
        
        # Fallback 1: Aggressive pruning
        aggressive_result = await self._attempt_aggressive_pruning(chroma_collection)
        
        if aggressive_result.success:
            # Retry search after pruning
            search_result = await self.search_engine.search(query, chroma_collection)
            return FallbackResult(
                strategy=FallbackStrategy.AGGRESSIVE_PRUNE,
                search_result=search_result,
                context_note="Context retrieved after aggressive pruning"
            )
        
        # Fallback 2: Query Redis short-term cache
        redis_result = await self._query_redis_cache(query)
        
        if redis_result.found:
            return FallbackResult(
                strategy=FallbackStrategy.REDIS_CACHE,
                search_result=redis_result,
                context_note="Context from short-term cache only"
            )
        
        # Fallback 3: Keyword-only search on metadata
        keyword_result = await self._keyword_only_search(query, chroma_collection)
        
        if keyword_result.results:
            return FallbackResult(
                strategy=FallbackStrategy.KEYWORD_ONLY,
                search_result=keyword_result,
                context_note="Keyword-only search (semantic search unavailable)"
            )
        
        # Fallback 4: Empty context
        return FallbackResult(
            strategy=FallbackStrategy.EMPTY_CONTEXT,
            search_result=None,
            context_note="No context available - operating without RAG",
            warning=True
        )
    
    async def _attempt_aggressive_pruning(self, chroma_collection) -> PruningResult:
        """
        Emergency pruning to free up space
        """
        # Temporarily lower threshold and increase prune ratio
        original_threshold = self.pruning_engine.COMPACTION_THRESHOLD
        original_ratio = self.pruning_engine.PRUNE_TARGET_RATIO
        
        try:
            self.pruning_engine.COMPACTION_THRESHOLD = 0.80
            self.pruning_engine.PRUNE_TARGET_RATIO = 0.20
            
            result = await self.pruning_engine.prune_if_needed(chroma_collection)
            
            return PruningResult(
                success=result.vectors_deleted > 0,
                vectors_deleted=result.vectors_deleted
            )
            
        finally:
            # Restore original values
            self.pruning_engine.COMPACTION_THRESHOLD = original_threshold
            self.pruning_engine.PRUNE_TARGET_RATIO = original_ratio
```

---

## 2.4 Gemini Circuit Breaker

### 2.4.1 Overview

The Gemini Circuit Breaker prevents cascading failures when the Gemini Flash API experiences issues. It monitors for "Safety Block" responses and HTTP 429 (Rate Limit) errors, entering a 60-minute "Local Only Mode" when thresholds are exceeded.

### 2.4.2 Circuit Breaker State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CIRCUIT BREAKER STATE DIAGRAM                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                              ┌─────────────┐                                │
│            ┌──────────────── │   CLOSED    │ ◄──── Success threshold met   │
│            │   (Normal ops)  │    [00]     │                               │
│            │                 └──────┬──────┘                               │
│            │                        │ Failure count >= threshold           │
│            │                        ▼                                       │
│            │                 ┌─────────────┐                                │
│            │   Success       │    OPEN     │                                │
│            └──────────────── │    [01]     │ ────► Local Only Mode          │
│                              │  (Blocking) │      (60 min cooldown)         │
│                              └──────┬──────┘                                │
│                                     │                                        │
│                                     │ Cooldown expired                       │
│                                     ▼                                        │
│                              ┌─────────────┐                                │
│                              │  HALF_OPEN  │                                │
│                              │    [10]     │                                │
│                              │ (Testing)   │                                │
│                              └─────────────┘                                │
│                                                                             │
│   State Transitions:                                                        │
│   - CLOSED → OPEN: Failure count >= FAILURE_THRESHOLD (5)                  │
│   - OPEN → HALF_OPEN: Cooldown timer (60 min) expires                      │
│   - HALF_OPEN → CLOSED: Test request succeeds                              │
│   - HALF_OPEN → OPEN: Test request fails                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4.3 State Definitions and Transitions

```python
class CircuitBreakerState(Enum):
    """
    Circuit Breaker State Enumeration
    
    CLOSED [0x00]: Normal operation, requests pass through
    OPEN [0x01]: Blocking state, all requests fail fast
    HALF_OPEN [0x10]: Testing state, limited requests allowed
    """
    CLOSED = 0x00
    OPEN = 0x01
    HALF_OPEN = 0x10

class CircuitBreakerConfig:
    """
    Circuit Breaker Configuration
    """
    # Failure threshold
    FAILURE_THRESHOLD = 5           # Failures before opening circuit
    FAILURE_WINDOW_SECONDS = 300    # Count failures within 5-minute window
    
    # Cooldown settings
    COOLDOWN_MINUTES = 60           # Local Only Mode duration
    COOLDOWN_SECONDS = COOLDOWN_MINUTES * 60
    
    # Half-open settings
    HALF_OPEN_MAX_REQUESTS = 3      # Max test requests in half-open
    HALF_OPEN_SUCCESS_THRESHOLD = 2 # Successes needed to close
    
    # Specific error detection
    SAFETY_BLOCK_CODES = ['SAFETY', 'BLOCKED', 'CONTENT_FILTERED']
    RATE_LIMIT_HTTP_CODE = 429

class CircuitBreaker:
    """
    Gemini API Circuit Breaker Implementation
    """
    
    def __init__(self):
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.failure_timestamps = deque(maxlen=CircuitBreakerConfig.FAILURE_THRESHOLD * 2)
        self.last_failure_time = None
        self.cooldown_end_time = None
        self.half_open_requests = 0
        self.half_open_successes = 0
        self.lock = threading.RLock()
        
    async def call(self, request_func: Callable, *args, **kwargs) -> CallResult:
        """
        Execute API call with circuit breaker protection
        """
        with self.lock:
            current_state = self.state
        
        if current_state == CircuitBreakerState.OPEN:
            # Check if cooldown has expired
            if await self._check_cooldown_expired():
                await self._transition_to_half_open()
            else:
                return CallResult(
                    success=False,
                    error="Circuit breaker OPEN - Local Only Mode active",
                    circuit_state=CircuitBreakerState.OPEN,
                    local_only=True
                )
        
        if current_state == CircuitBreakerState.HALF_OPEN:
            with self.lock:
                if self.half_open_requests >= CircuitBreakerConfig.HALF_OPEN_MAX_REQUESTS:
                    return CallResult(
                        success=False,
                        error="Circuit breaker HALF_OPEN - Test quota exhausted",
                        circuit_state=CircuitBreakerState.HALF_OPEN
                    )
                self.half_open_requests += 1
        
        # Execute the request
        try:
            result = await request_func(*args, **kwargs)
            await self._on_success()
            return CallResult(
                success=True,
                result=result,
                circuit_state=self.state
            )
            
        except Exception as e:
            await self._on_failure(e)
            return CallResult(
                success=False,
                error=str(e),
                circuit_state=self.state,
                failure_type=self._classify_failure(e)
            )
```

### 2.4.4 Failure Counting Mechanism

```python
class FailureCounter:
    """
    Sliding window failure counter with error classification
    """
    
    def __init__(self):
        self.failures = deque()
        self.lock = threading.RLock()
        
    async def record_failure(self, error: Exception, 
                             timestamp: Optional[float] = None) -> FailureRecord:
        """
        Record a failure with classification
        """
        if timestamp is None:
            timestamp = time.time()
        
        failure_type = self._classify_failure(error)
        
        record = FailureRecord(
            timestamp=timestamp,
            error_type=type(error).__name__,
            failure_category=failure_type,
            error_message=str(error)[:200],  # Truncate long messages
            http_code=self._extract_http_code(error)
        )
        
        with self.lock:
            self.failures.append(record)
            self._expire_old_failures(timestamp)
        
        return record
    
    def _classify_failure(self, error: Exception) -> FailureCategory:
        """
        Classify failure type for circuit breaker logic
        """
        error_str = str(error).upper()
        error_type = type(error).__name__
        
        # Check for safety block
        if any(code in error_str for code in CircuitBreakerConfig.SAFETY_BLOCK_CODES):
            return FailureCategory.SAFETY_BLOCK
        
        # Check for rate limit
        http_code = self._extract_http_code(error)
        if http_code == CircuitBreakerConfig.RATE_LIMIT_HTTP_CODE:
            return FailureCategory.RATE_LIMIT
        
        # Check for network errors
        if error_type in ['ConnectionError', 'TimeoutError', 'NetworkError']:
            return FailureCategory.NETWORK
        
        # Check for authentication errors
        if http_code == 401 or 'AUTHENTICATION' in error_str:
            return FailureCategory.AUTHENTICATION
        
        # Default: API error
        return FailureCategory.API_ERROR
    
    def _extract_http_code(self, error: Exception) -> Optional[int]:
        """Extract HTTP status code from exception"""
        # Check for HTTPError with code attribute
        if hasattr(error, 'code'):
            return error.code
        
        if hasattr(error, 'status'):
            return error.status
        
        # Parse from error message
        error_str = str(error)
        match = re.search(r'\b(4\d{2}|5\d{2})\b', error_str)
        if match:
            return int(match.group(1))
        
        return None
    
    def get_recent_failure_count(self, 
                                  window_seconds: float = None,
                                  category: FailureCategory = None) -> int:
        """
        Get failure count within time window, optionally filtered by category
        """
        if window_seconds is None:
            window_seconds = CircuitBreakerConfig.FAILURE_WINDOW_SECONDS
        
        cutoff_time = time.time() - window_seconds
        
        with self.lock:
            self._expire_old_failures(time.time())
            
            if category is None:
                return sum(1 for f in self.failures if f.timestamp >= cutoff_time)
            else:
                return sum(
                    1 for f in self.failures 
                    if f.timestamp >= cutoff_time and f.failure_category == category
                )
    
    def _expire_old_failures(self, current_time: float):
        """Remove failures older than the window"""
        cutoff = current_time - CircuitBreakerConfig.FAILURE_WINDOW_SECONDS
        
        while self.failures and self.failures[0].timestamp < cutoff:
            self.failures.popleft()
```

### 2.4.5 State Transition Logic

```python
class CircuitBreakerStateManager:
    """
    Manages circuit breaker state transitions
    """
    
    async def transition(self, from_state: CircuitBreakerState,
                         to_state: CircuitBreakerState,
                         reason: str) -> TransitionResult:
        """
        Execute state transition with logging
        """
        
        self.logger.warning(
            f"CIRCUIT_BREAKER_TRANSITION: "
            f"{from_state.name} -> {to_state.name}, "
            f"reason={reason}"
        )
        
        # Execute transition-specific actions
        if to_state == CircuitBreakerState.OPEN:
            await self._on_open(reason)
        elif to_state == CircuitBreakerState.HALF_OPEN:
            await self._on_half_open()
        elif to_state == CircuitBreakerState.CLOSED:
            await self._on_close()
        
        return TransitionResult(
            from_state=from_state,
            to_state=to_state,
            timestamp=time.time(),
            reason=reason
        )
    
    async def _on_open(self, reason: str):
        """
        Actions when circuit opens (entering Local Only Mode)
        """
        # Set cooldown end time
        self.cooldown_end_time = time.time() + CircuitBreakerConfig.COOLDOWN_SECONDS
        
        # Log the event
        self.logger.critical(
            f"CIRCUIT_BREAKER_OPENED: "
            f"reason={reason}, "
            f"cooldown_until={datetime.fromtimestamp(self.cooldown_end_time)}, "
            f"local_only_mode=ENABLED"
        )
        
        # Notify monitoring
        await self._notify_monitoring('circuit_opened', {
            'reason': reason,
            'cooldown_seconds': CircuitBreakerConfig.COOLDOWN_SECONDS,
            'failure_count': self.failure_counter.get_recent_failure_count()
        })
        
        # Switch to local model
        await self._activate_local_only_mode()
    
    async def _on_half_open(self):
        """
        Actions when entering half-open state
        """
        self.half_open_requests = 0
        self.half_open_successes = 0
        
        self.logger.info("CIRCUIT_BREAKER_HALF_OPEN: Testing Gemini availability")
        
        # Send test request
        await self._send_test_request()
    
    async def _on_close(self):
        """
        Actions when circuit closes (returning to normal)
        """
        # Reset failure count
        self.failure_count = 0
        self.failure_counter.clear()
        
        self.logger.info("CIRCUIT_BREAKER_CLOSED: Returning to normal operation")
        
        # Notify monitoring
        await self._notify_monitoring('circuit_closed', {
            'half_open_successes': self.half_open_successes,
            'total_downtime_seconds': self._calculate_downtime()
        })
        
        # Disable local only mode
        await self._deactivate_local_only_mode()
```

### 2.4.6 60-Minute Cooldown Implementation

```python
class CooldownManager:
    """
    Manages the 60-minute Local Only Mode cooldown
    """
    
    COOLDOWN_SECONDS = 60 * 60  # 60 minutes
    
    def __init__(self):
        self.cooldown_end_time = None
        self.cooldown_task = None
        self.on_cooldown_complete = None
        
    async def start_cooldown(self, on_complete: Callable):
        """
        Start the 60-minute cooldown timer
        """
        self.cooldown_end_time = time.time() + self.COOLDOWN_SECONDS
        self.on_cooldown_complete = on_complete
        
        self.logger.info(
            f"COOLDOWN_START: "
            f"duration=60min, "
            f"ends_at={datetime.fromtimestamp(self.cooldown_end_time)}"
        )
        
        # Start async cooldown task
        self.cooldown_task = asyncio.create_task(self._cooldown_loop())
        
    async def _cooldown_loop(self):
        """
        Async cooldown loop with progress logging
        """
        while time.time() < self.cooldown_end_time:
            remaining = self.cooldown_end_time - time.time()
            
            # Log progress every 10 minutes
            if int(remaining) % 600 == 0:
                minutes_remaining = int(remaining / 60)
                self.logger.info(f"COOLDOWN_PROGRESS: {minutes_remaining} minutes remaining")
            
            # Sleep in small increments to allow cancellation
            await asyncio.sleep(1)
        
        # Cooldown complete
        self.logger.info("COOLDOWN_COMPLETE: Transitioning to HALF_OPEN")
        
        if self.on_cooldown_complete:
            await self.on_cooldown_complete()
    
    def get_remaining_seconds(self) -> float:
        """Get remaining cooldown time"""
        if self.cooldown_end_time is None:
            return 0
        
        remaining = self.cooldown_end_time - time.time()
        return max(0, remaining)
    
    def get_remaining_minutes(self) -> int:
        """Get remaining cooldown time in minutes"""
        return int(self.get_remaining_seconds() / 60)
    
    def is_in_cooldown(self) -> bool:
        """Check if currently in cooldown period"""
        return self.get_remaining_seconds() > 0
    
    async def cancel_cooldown(self):
        """Cancel active cooldown (for manual override)"""
        if self.cooldown_task:
            self.cooldown_task.cancel()
            try:
                await self.cooldown_task
            except asyncio.CancelledError:
                pass
        
        self.cooldown_end_time = None
        self.logger.info("COOLDOWN_CANCELLED: Manual override")
```

### 2.4.7 Rate Limit Detection (429 Handling)

```python
class RateLimitDetector:
    """
    Detects and handles HTTP 429 (Rate Limit) errors
    """
    
    RATE_LIMIT_HTTP_CODE = 429
    
    def detect_rate_limit(self, error: Exception) -> RateLimitInfo:
        """
        Detect if error is a rate limit and extract retry information
        """
        http_code = self._extract_http_code(error)
        
        if http_code != self.RATE_LIMIT_HTTP_CODE:
            return RateLimitInfo(is_rate_limit=False)
        
        # Extract retry-after header if available
        retry_after = self._extract_retry_after(error)
        
        # Extract rate limit details
        limit_info = self._parse_rate_limit_headers(error)
        
        return RateLimitInfo(
            is_rate_limit=True,
            retry_after_seconds=retry_after,
            limit=limit_info.get('limit'),
            remaining=limit_info.get('remaining'),
            reset_timestamp=limit_info.get('reset')
        )
    
    def _extract_retry_after(self, error: Exception) -> Optional[int]:
        """Extract Retry-After header value"""
        # Check for response object with headers
        if hasattr(error, 'headers'):
            retry_after = error.headers.get('Retry-After')
            if retry_after:
                try:
                    return int(retry_after)
                except ValueError:
                    # Might be HTTP date format
                    pass
        
        # Check for response attribute
        if hasattr(error, 'response') and error.response:
            retry_after = error.response.headers.get('Retry-After')
            if retry_after:
                try:
                    return int(retry_after)
                except ValueError:
                    pass
        
        # Default: no retry-after specified
        return None
    
    def _parse_rate_limit_headers(self, error: Exception) -> Dict:
        """Parse X-RateLimit-* headers"""
        headers = {}
        
        source = None
        if hasattr(error, 'headers'):
            source = error.headers
        elif hasattr(error, 'response') and error.response:
            source = error.response.headers
        
        if source:
            headers['limit'] = source.get('X-RateLimit-Limit')
            headers['remaining'] = source.get('X-RateLimit-Remaining')
            headers['reset'] = source.get('X-RateLimit-Reset')
        
        return headers
    
    async def handle_rate_limit(self, rate_limit_info: RateLimitInfo) -> HandlerAction:
        """
        Determine action based on rate limit information
        """
        
        if rate_limit_info.retry_after_seconds:
            # Use server's suggested retry time
            if rate_limit_info.retry_after_seconds > 300:  # > 5 minutes
                # Too long - trigger circuit breaker
                return HandlerAction(
                    action=Action.TRIGGER_CIRCUIT_BREAKER,
                    reason=f"Rate limit retry_after={rate_limit_info.retry_after_seconds}s too long"
                )
            else:
                # Short retry - wait and retry
                return HandlerAction(
                    action=Action.RETRY_AFTER_DELAY,
                    delay_seconds=rate_limit_info.retry_after_seconds + 1
                )
        
        # No retry-after specified - use exponential backoff
        return HandlerAction(
            action=Action.EXPONENTIAL_BACKOFF,
            base_delay=5,
            max_delay=60
        )
```

### 2.4.8 Safety Block Detection and Logging

```python
class SafetyBlockDetector:
    """
    Detects Gemini safety block responses
    """
    
    SAFETY_BLOCK_INDICATORS = [
        'SAFETY',
        'BLOCKED',
        'CONTENT_FILTERED',
        'HARM_CATEGORY',
        'SAFETY_RATING',
        'BLOCK_REASON'
    ]
    
    SAFETY_CATEGORIES = [
        'HARM_CATEGORY_HARASSMENT',
        'HARM_CATEGORY_HATE_SPEECH',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT',
        'HARM_CATEGORY_DANGEROUS_CONTENT'
    ]
    
    def detect_safety_block(self, response: Any) -> SafetyBlockInfo:
        """
        Detect if response contains a safety block
        """
        response_str = str(response).upper()
        
        # Check for safety block indicators
        is_blocked = any(
            indicator in response_str 
            for indicator in self.SAFETY_BLOCK_INDICATORS
        )
        
        if not is_blocked:
            return SafetyBlockInfo(is_blocked=False)
        
        # Extract safety details
        categories = self._extract_safety_categories(response)
        block_reason = self._extract_block_reason(response)
        
        return SafetyBlockInfo(
            is_blocked=True,
            categories=categories,
            block_reason=block_reason,
            raw_response=str(response)[:500]  # Truncate for logging
        )
    
    def _extract_safety_categories(self, response: Any) -> List[str]:
        """Extract which safety categories were triggered"""
        categories = []
        response_str = str(response).upper()
        
        for category in self.SAFETY_CATEGORIES:
            if category in response_str:
                categories.append(category)
        
        return categories
    
    def _extract_block_reason(self, response: Any) -> Optional[str]:
        """Extract the specific block reason"""
        # Try to parse structured response
        if hasattr(response, 'prompt_feedback'):
            feedback = response.prompt_feedback
            if hasattr(feedback, 'block_reason'):
                return str(feedback.block_reason)
        
        # Fallback: search in string
        response_str = str(response)
        match = re.search(r'block_reason["\']?\s*[:=]\s*["\']?([^"\']+)', response_str, re.I)
        if match:
            return match.group(1)
        
        return None
    
    async def log_safety_block(self, safety_info: SafetyBlockInfo, 
                                request_context: Dict):
        """
        Log safety block with full context (without sensitive content)
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'SAFETY_BLOCK',
            'categories': safety_info.categories,
            'block_reason': safety_info.block_reason,
            'request_type': request_context.get('request_type', 'unknown'),
            'request_hash': hashlib.sha256(
                str(request_context.get('prompt', '')).encode()
            ).hexdigest()[:16],  # Hash for correlation without storing content
            'model_version': request_context.get('model_version', 'unknown')
        }
        
        # Log at WARNING level
        self.logger.warning(f"SAFETY_BLOCK_DETECTED: {json.dumps(log_entry)}")
        
        # Also write to dedicated safety log
        await self._write_to_safety_log(log_entry)
        
        # Update circuit breaker failure counter
        await self.circuit_breaker.record_failure(
            Exception(f"Safety block: {safety_info.block_reason}"),
            failure_type=FailureCategory.SAFETY_BLOCK
        )
```

### 2.4.9 Complete Circuit Breaker Integration

```python
class GeminiCircuitBreakerIntegration:
    """
    Complete integration of circuit breaker with Gemini API calls
    """
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.rate_limit_detector = RateLimitDetector()
        self.safety_block_detector = SafetyBlockDetector()
        self.failure_counter = FailureCounter()
        self.local_only_mode = False
        
    async def generate_content(self, prompt: str, 
                                fallback_to_local: bool = True) -> GenerationResult:
        """
        Generate content with full circuit breaker protection
        """
        
        # Check circuit breaker state
        cb_state = self.circuit_breaker.state
        
        if cb_state == CircuitBreakerState.OPEN:
            if fallback_to_local:
                return await self._fallback_to_local_model(prompt)
            else:
                return GenerationResult(
                    success=False,
                    error="Circuit breaker OPEN - Gemini unavailable",
                    circuit_state=cb_state
                )
        
        # Attempt Gemini API call
        try:
            response = await self._call_gemini_api(prompt)
            
            # Check for safety block in response
            safety_info = self.safety_block_detector.detect_safety_block(response)
            
            if safety_info.is_blocked:
                await self.safety_block_detector.log_safety_block(
                    safety_info,
                    {'prompt': prompt, 'request_type': 'generate_content'}
                )
                
                await self.failure_counter.record_failure(
                    Exception(f"Safety block: {safety_info.block_reason}")
                )
                
                if fallback_to_local:
                    return await self._fallback_to_local_model(prompt)
                else:
                    return GenerationResult(
                        success=False,
                        error=f"Safety block: {safety_info.block_reason}",
                        circuit_state=cb_state,
                        safety_blocked=True
                    )
            
            # Success - record and return
            await self.circuit_breaker._on_success()
            
            return GenerationResult(
                success=True,
                content=response.text,
                circuit_state=CircuitBreakerState.CLOSED,
                model_used='gemini-flash'
            )
            
        except Exception as e:
            # Detect failure type
            rate_limit_info = self.rate_limit_detector.detect_rate_limit(e)
            
            if rate_limit_info.is_rate_limit:
                await self.failure_counter.record_failure(e)
                
                # Check if we should trigger circuit breaker
                recent_failures = self.failure_counter.get_recent_failure_count(
                    category=FailureCategory.RATE_LIMIT
                )
                
                if recent_failures >= CircuitBreakerConfig.FAILURE_THRESHOLD:
                    await self.circuit_breaker._transition_to_open(
                        reason=f"Rate limit threshold exceeded: {recent_failures} failures"
                    )
                
                if fallback_to_local:
                    return await self._fallback_to_local_model(prompt)
                else:
                    return GenerationResult(
                        success=False,
                        error=f"Rate limit: {e}",
                        circuit_state=self.circuit_breaker.state,
                        retry_after=rate_limit_info.retry_after_seconds
                    )
            
            # Other error - record and potentially trigger circuit breaker
            await self.failure_counter.record_failure(e)
            
            total_failures = self.failure_counter.get_recent_failure_count()
            
            if total_failures >= CircuitBreakerConfig.FAILURE_THRESHOLD:
                await self.circuit_breaker._transition_to_open(
                    reason=f"Failure threshold exceeded: {total_failures} failures"
                )
            
            if fallback_to_local:
                return await self._fallback_to_local_model(prompt)
            else:
                return GenerationResult(
                    success=False,
                    error=str(e),
                    circuit_state=self.circuit_breaker.state
                )
    
    async def _fallback_to_local_model(self, prompt: str) -> GenerationResult:
        """
        Fallback to local Qwen Coder model
        """
        self.logger.info("FALLBACK_TO_LOCAL: Using Qwen Coder 7B")
        
        try:
            # Ensure Qwen Coder is loaded
            await self.vram_mutex.load_model('qwen_coder')
            
            # Generate with local model
            response = await self.local_model.generate(prompt)
            
            return GenerationResult(
                success=True,
                content=response,
                circuit_state=self.circuit_breaker.state,
                model_used='qwen-coder-7b-local',
                fallback=True
            )
            
        except Exception as e:
            self.logger.error(f"FALLBACK_FAILED: {e}")
            return GenerationResult(
                success=False,
                error=f"Both Gemini and local model failed: {e}",
                circuit_state=self.circuit_breaker.state
            )
```

---

## Appendix A: Error Codes Reference

| Code | Name | Description |
|------|------|-------------|
| 0x00 | SUCCESS | Operation completed successfully |
| 0x10 | VRAM_TIMEOUT | VRAM operation exceeded timeout |
| 0x11 | UNLOAD_HANG | Model unload hung for >29 seconds |
| 0x12 | PROCESS_KILL_FAILED | Failed to kill hung process |
| 0x13 | GPU_UNRECOVERABLE | GPU in unrecoverable state |
| 0x20 | CHROMADB_FULL | Vector store at capacity |
| 0x21 | PRUNE_FAILED | Vector pruning operation failed |
| 0x30 | CIRCUIT_OPEN | Circuit breaker is open |
| 0x31 | SAFETY_BLOCK | Content blocked by safety filter |
| 0x32 | RATE_LIMIT | API rate limit exceeded |

---

## Appendix B: Configuration Summary

| Component | Parameter | Value |
|-----------|-----------|-------|
| VRAM Mutex | Hard Timeout | 30 seconds |
| VRAM Mutex | Process Kill Timeout | 10 seconds |
| VRAM Mutex | Recovery Cooldown | 60 seconds |
| ChromaDB | Max Vectors | 100,000 |
| ChromaDB | Compaction Threshold | 90% |
| ChromaDB | Prune Target | 10% |
| Redis | Max Memory | 512 MB |
| Circuit Breaker | Failure Threshold | 5 failures |
| Circuit Breaker | Failure Window | 5 minutes |
| Circuit Breaker | Cooldown | 60 minutes |

---

*End of Section 2 (Part A): Short-Term Operational Logic - VRAM Mutex & Context Management*
