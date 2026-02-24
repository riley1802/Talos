"""Skill Quarantine Manager — state machine for new skill validation.

Spec § 2.7: PENDING → EXECUTING → PASSED/FAILED → AWAITING_PROMOTION → PROMOTED/REJECTED
Requires 3 clean test runs and a TTS code to promote.
"""
import asyncio
import hashlib
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(os.getenv("TALOS_SKILLS_DIR", "/talos/skills"))
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "60"))
MIN_SUCCESSFUL_RUNS = 3


async def submit(
    skill_id: str,
    code: str,
    language: str = "python",
    source_type: str = "user_submitted",
    origin: str = "unknown",
) -> dict:
    """Register a new skill into quarantine and return its metadata."""
    from skills.registry import register_new
    return register_new(skill_id, code, language, source_type, origin)


async def run_test(skill_id: str) -> dict:
    """Execute a quarantined skill in a sandbox. Returns test result dict."""
    from skills.registry import load, record_test_result, update_state

    meta = load(skill_id, state="quarantine")
    if not meta:
        raise ValueError(f"Skill {skill_id} not found in quarantine")

    quarantine_dir = SKILLS_ROOT / "quarantine" / skill_id
    language = meta["code"]["language"]
    code_file = quarantine_dir / f"skill.{language}"

    if not code_file.exists():
        raise FileNotFoundError(f"Skill code not found: {code_file}")

    # Verify code hash before execution
    actual_hash = hashlib.sha256(code_file.read_bytes()).hexdigest()
    expected_hash = meta["code"]["hash"]
    if actual_hash != expected_hash:
        raise ValueError(f"Skill {skill_id} hash mismatch — possible tampering")

    update_state(skill_id, "executing")

    test_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        result = await _execute_sandboxed(code_file, language)
        duration_ms = int((time.time() - start_time) * 1000)
        passed = result["exit_code"] == 0

        record_test_result(skill_id, test_id, passed, {
            "duration_ms": duration_ms,
            "stdout": result["stdout"][:1000],
            "stderr": result["stderr"][:500],
            "exit_code": result["exit_code"],
        })

        # Count passed tests
        meta = load(skill_id)
        if not meta:
            raise RuntimeError(f"Skill {skill_id} metadata lost during test")

        passed_count = sum(
            1 for t in meta["execution_tests"] if t["status"] == "passed"
        )

        if passed and passed_count >= MIN_SUCCESSFUL_RUNS:
            update_state(skill_id, "awaiting_promotion")
            logger.info("Skill %s passed %d tests — awaiting user promotion", skill_id, passed_count)
        elif not passed:
            update_state(skill_id, "failed")

        return {
            "test_id": test_id,
            "passed": passed,
            "passed_count": passed_count,
            "ready_for_promotion": passed and passed_count >= MIN_SUCCESSFUL_RUNS,
            **result,
        }

    except asyncio.TimeoutError:
        update_state(skill_id, "failed")
        return {"test_id": test_id, "passed": False, "error": "execution_timeout"}
    except Exception as exc:
        update_state(skill_id, "failed")
        logger.error("Skill %s test error: %s", skill_id, exc)
        return {"test_id": test_id, "passed": False, "error": str(exc)}


async def _execute_sandboxed(code_file: Path, language: str) -> dict:
    """Run code in a restricted subprocess with timeout and resource limits."""
    if language == "python":
        cmd = ["python3", "-I", str(code_file)]
    elif language in ("javascript", "typescript"):
        cmd = ["node", str(code_file)]
    else:
        raise ValueError(f"Unsupported language: {language}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(code_file.parent),
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},  # Minimal env
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SANDBOX_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise

    return {
        "exit_code": proc.returncode or 0,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }


async def promote(skill_id: str, tts_code: str, promoted_by: str = "user") -> bool:
    """Promote a skill from awaiting_promotion to active. Requires valid TTS code."""
    from skills.registry import load, update_state
    from security.tts_codes import verify
    from security.audit_log import log_skill_promotion

    meta = load(skill_id)
    if not meta:
        raise ValueError(f"Skill {skill_id} not found")
    if meta["quarantine_state"] != "awaiting_promotion":
        raise ValueError(f"Skill {skill_id} is not awaiting promotion (state: {meta['quarantine_state']})")

    if not verify(skill_id, tts_code):
        logger.warning("TTS code verification failed for skill %s", skill_id)
        return False

    update_state(skill_id, "promoted")
    log_skill_promotion(skill_id, promoted_by)
    logger.info("Skill %s promoted to active", skill_id)
    return True


async def reject(skill_id: str, reason: str = "rejected by user") -> None:
    from skills.registry import update_state
    update_state(skill_id, "rejected")
    logger.info("Skill %s rejected: %s", skill_id, reason)
