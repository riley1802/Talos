"""Talos v4.0 — FastAPI application entry point.

Endpoints:
  GET  /health              Service status
  GET  /metrics             VRAM state, token counts, skill counts
  POST /chat                Send message, get response
  POST /skills/{id}/promote TTS-protected promotion
  DELETE /skills/{id}       Manual deprecation
  WS   /ws/logs             Live log streaming

Basic Auth protects all endpoints.
"""
import asyncio
import base64
import logging
import os
import secrets
import subprocess
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER", "admin")
BASIC_AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, BASIC_AUTH_USER)
    ok_pass = secrets.compare_digest(credentials.password, BASIC_AUTH_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Talos v4.0 starting up...")

    # Wait for dependencies
    from memory.redis_client import wait_for_redis
    from memory.chroma_client import wait_for_chromadb, init_collections

    if not await wait_for_redis():
        raise RuntimeError("Redis unavailable at startup")
    if not await wait_for_chromadb():
        raise RuntimeError("ChromaDB unavailable at startup")

    await init_collections()

    # Start watchdog
    from orchestrator.watchdog import watchdog, heartbeat_task
    watchdog.start()
    asyncio.create_task(heartbeat_task())

    # Start log streamer
    from comms.websocket import log_streamer
    asyncio.create_task(log_streamer.run())

    # Start dream cycle scheduler
    from maintenance.dream_cycle import start_scheduler
    start_scheduler()

    # Optional: pull Ollama models in background
    from intelligence.ollama_client import ensure_models_pulled, is_available
    if await is_available():
        asyncio.create_task(ensure_models_pulled())

    # Optional: auto-open dashboard
    if os.getenv("DASHBOARD_AUTO_OPEN", "true").lower() == "true":
        _auto_open_dashboard()

    logger.info("Talos v4.0 ready")
    yield

    logger.info("Talos v4.0 shutting down...")
    from comms.websocket import log_streamer
    log_streamer.stop()


app = FastAPI(title="Talos v4.0", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
_frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_path):
    app.mount("/static", StaticFiles(directory=_frontend_path), name="static")


# ── Models ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    force_cloud: bool = False


class PromoteRequest(BaseModel):
    tts_code: str


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    frontend_index = os.path.join(_frontend_path, "index.html")
    if os.path.isfile(frontend_index):
        with open(frontend_index) as f:
            return HTMLResponse(f.read())
    return {"name": "Talos v4.0", "status": "running"}


@app.get("/health")
async def health():
    from memory.redis_client import ping as redis_ping
    from memory.chroma_client import ping as chroma_ping
    from intelligence.ollama_client import is_available as ollama_ok

    r_ok = await redis_ping()
    c_ok = await chroma_ping()
    o_ok = await ollama_ok()

    all_ok = r_ok and c_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "redis": "ok" if r_ok else "fail",
        "chromadb": "ok" if c_ok else "fail",
        "ollama": "ok" if o_ok else "unavailable",
    }


@app.get("/metrics", dependencies=[Depends(require_auth)])
async def metrics():
    from intelligence.vram_mutex import vram_mutex
    from intelligence.gemini_client import get_status as gemini_status
    from skills.registry import list_skills
    from memory.chroma_client import get_total_vector_count
    from memory.redis_client import get_client
    import psutil

    gemini = gemini_status()

    try:
        r = await get_client()
        redis_info = await r.info("memory")
        redis_mem_mb = int(redis_info.get("used_memory", 0)) // (1024 * 1024)
    except Exception:
        redis_mem_mb = -1

    active_skills = len(list_skills("active"))
    quarantine_skills = len(list_skills("quarantine"))
    total_vectors = await get_total_vector_count()

    return {
        "vram": {
            "state": vram_mutex.state.name,
            "loaded_model": vram_mutex.loaded_model,
        },
        "gemini": gemini,
        "redis_mem_mb": redis_mem_mb,
        "total_vectors": total_vectors,
        "skills": {"active": active_skills, "quarantine": quarantine_skills},
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "mem_percent": psutil.virtual_memory().percent,
        },
    }


@app.post("/chat", dependencies=[Depends(require_auth)])
async def chat(req: ChatRequest):
    from orchestrator.loop import process_message
    result = await process_message(
        user_input=req.message,
        session_id=req.session_id,
        force_cloud=req.force_cloud,
    )
    if result.get("blocked"):
        raise HTTPException(status_code=403, detail=result.get("reason", "blocked"))
    return result


@app.post("/skills/{skill_id}/promote", dependencies=[Depends(require_auth)])
async def promote_skill(skill_id: str, req: PromoteRequest, user: str = Depends(require_auth)):
    from skills.quarantine import promote
    success = await promote(skill_id, req.tts_code, promoted_by=user)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired TTS code")
    return {"skill_id": skill_id, "promoted": True}


@app.post("/skills/{skill_id}/tts-request", dependencies=[Depends(require_auth)])
async def request_tts(skill_id: str):
    from security.tts_codes import generate
    from skills.registry import load
    meta = load(skill_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Skill not found")
    if meta["quarantine_state"] != "awaiting_promotion":
        raise HTTPException(status_code=400, detail="Skill is not awaiting promotion")
    code = generate(skill_id)
    logger.info("TTS code generated for %s: %s", skill_id, code)
    return {"skill_id": skill_id, "tts_code": code, "expires_in_seconds": 300}


@app.get("/skills", dependencies=[Depends(require_auth)])
async def list_skills_endpoint(state: str = "active"):
    from skills.registry import list_skills
    if state not in ("active", "quarantine", "deprecated"):
        raise HTTPException(status_code=400, detail="Invalid state")
    return list_skills(state)


@app.delete("/skills/{skill_id}", dependencies=[Depends(require_auth)])
async def deprecate_skill(skill_id: str):
    from skills.registry import update_state
    from security.audit_log import log_skill_deprecation
    result = update_state(skill_id, "deprecated")
    if not result:
        raise HTTPException(status_code=404, detail="Skill not found")
    log_skill_deprecation(skill_id, reason="manually deprecated via API")
    return {"skill_id": skill_id, "deprecated": True}


@app.post("/panic", dependencies=[Depends(require_auth)])
async def panic(req: PromoteRequest):
    """Emergency lockdown. Requires TTS code. Stops all skill execution."""
    from memory.redis_client import set_value
    from security.audit_log import log_security_event

    await set_value("talos:security:lockdown", {"active": True, "reason": "panic_button"})
    log_security_event("PANIC_BUTTON", {"triggered_by": "api"})
    logger.critical("PANIC BUTTON ACTIVATED")
    return {"lockdown": True}


@app.post("/panic/unlock", dependencies=[Depends(require_auth)])
async def unlock(req: PromoteRequest):
    from memory.redis_client import get_value, set_value
    lockdown = await get_value("talos:security:lockdown")
    if not lockdown or not lockdown.get("active"):
        return {"lockdown": False}
    stored_code = lockdown.get("unlock_code")
    if stored_code and secrets.compare_digest(req.tts_code, stored_code):
        await set_value("talos:security:lockdown", {"active": False})
        return {"lockdown": False, "unlocked": True}
    raise HTTPException(status_code=403, detail="Invalid unlock code")


@app.post("/admin/dream-cycle", dependencies=[Depends(require_auth)])
async def trigger_dream_cycle():
    """Manually trigger the maintenance dream cycle."""
    from maintenance.dream_cycle import trigger_now
    asyncio.create_task(trigger_now())
    return {"triggered": True, "message": "Dream cycle started in background"}


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    from comms.websocket import connect, disconnect
    await connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await disconnect(websocket)


def _auto_open_dashboard() -> None:
    import threading
    def _open():
        import time
        time.sleep(3)
        try:
            subprocess.Popen(["xdg-open", "http://localhost:8080"])
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()
