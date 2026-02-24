"""Skill registry — metadata CRUD for all skills across all states.

Each skill has a JSON metadata file alongside its code.
States: quarantine | active | deprecated
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(os.getenv("TALOS_SKILLS_DIR", "/talos/skills"))
SKILL_MAX_SIZE = int(os.getenv("SKILL_MAX_SIZE_BYTES", "1048576"))  # 1MB


def _meta_path(skill_id: str, state: str) -> Path:
    return SKILLS_ROOT / state / skill_id / "metadata.json"


def _skill_dir(skill_id: str, state: str) -> Path:
    return SKILLS_ROOT / state / skill_id


def load(skill_id: str, state: Optional[str] = None) -> Optional[dict]:
    """Load skill metadata. Searches all states if state not specified."""
    states = [state] if state else ["active", "quarantine", "deprecated"]
    for s in states:
        path = _meta_path(skill_id, s)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception as exc:
                logger.error("Failed to load metadata for %s/%s: %s", s, skill_id, exc)
    return None


def save(metadata: dict) -> None:
    skill_id = metadata["skill_id"]
    state = metadata["quarantine_state"]

    # Map state to directory
    if state in ("pending", "executing", "passed", "failed", "awaiting_promotion"):
        dir_name = "quarantine"
    elif state == "promoted":
        dir_name = "active"
    elif state in ("rejected", "deprecated"):
        dir_name = "deprecated"
    else:
        dir_name = "quarantine"

    path = _meta_path(skill_id, dir_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2))


def list_skills(state: str) -> list[dict]:
    state_dir = SKILLS_ROOT / state
    if not state_dir.exists():
        return []
    skills = []
    for meta_file in state_dir.glob("*/metadata.json"):
        try:
            skills.append(json.loads(meta_file.read_text()))
        except Exception:
            pass
    return skills


def register_new(
    skill_id: str,
    code: str,
    language: str,
    source_type: str,
    origin: str,
) -> dict:
    """Create and persist a new skill in quarantine state."""
    if len(code.encode()) > SKILL_MAX_SIZE:
        raise ValueError(f"Skill code exceeds {SKILL_MAX_SIZE} byte limit")

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    now = time.time()

    metadata = {
        "skill_id": skill_id,
        "version": "0.1.0",
        "quarantine_state": "pending",
        "created_at": now,
        "updated_at": now,
        "source": {"type": source_type, "origin": origin},
        "code": {
            "hash": code_hash,
            "size_bytes": len(code.encode()),
            "language": language,
        },
        "execution_tests": [],
        "strike_count": 0,
        "promotion_requirements": {
            "min_successful_executions": 3,
            "require_user_confirmation": True,
        },
    }

    # Write code file
    code_dir = _skill_dir(skill_id, "quarantine")
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / f"skill.{language}").write_text(code)
    save(metadata)
    logger.info("Skill %s registered in quarantine", skill_id)
    return metadata


def update_state(skill_id: str, new_state: str) -> Optional[dict]:
    meta = load(skill_id)
    if not meta:
        return None
    old_state = meta["quarantine_state"]
    meta["quarantine_state"] = new_state
    meta["updated_at"] = time.time()

    old_dir_name = _dir_for_state(old_state)
    new_dir_name = _dir_for_state(new_state)

    if old_dir_name != new_dir_name:
        old_dir = _skill_dir(skill_id, old_dir_name)
        new_dir = _skill_dir(skill_id, new_dir_name)
        if old_dir.exists():
            import shutil
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))

    save(meta)
    return meta


def _dir_for_state(state: str) -> str:
    if state in ("pending", "executing", "passed", "failed", "awaiting_promotion"):
        return "quarantine"
    if state == "promoted":
        return "active"
    return "deprecated"


def record_test_result(skill_id: str, test_id: str, passed: bool, details: dict) -> None:
    meta = load(skill_id)
    if not meta:
        return
    meta["execution_tests"].append({
        "test_id": test_id,
        "status": "passed" if passed else "failed",
        "executed_at": time.time(),
        **details,
    })
    meta["updated_at"] = time.time()
    save(meta)


def increment_strike(skill_id: str) -> int:
    meta = load(skill_id)
    if not meta:
        return 0
    meta["strike_count"] = meta.get("strike_count", 0) + 1
    meta["updated_at"] = time.time()
    save(meta)
    return meta["strike_count"]
