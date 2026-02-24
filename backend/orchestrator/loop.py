"""Central orchestrator loop.

Message flow:
  receive → firewall → RAG context inject → route to model → store response → return
"""
import asyncio
import logging
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


async def process_message(
    user_input: str,
    session_id: Optional[str] = None,
    images: Optional[list[str]] = None,
    force_cloud: bool = False,
) -> dict:
    """
    Full message processing pipeline. Returns a response dict.
    """
    correlation_id = str(uuid.uuid4())
    session_id = session_id or correlation_id
    start_time = time.time()

    logger.info("[%s] Processing message (len=%d)", correlation_id, len(user_input))

    # Step 1: Firewall check
    from skills.firewall import scan, ThreatLevel
    fw_result = scan(user_input)
    if not fw_result.allowed:
        logger.warning("[%s] Message blocked by firewall: %s", correlation_id, fw_result.detections)
        return {
            "correlation_id": correlation_id,
            "blocked": True,
            "reason": "security_policy",
            "detections": fw_result.detections,
            "response": None,
        }

    # Step 2: Check lockdown state
    from memory.redis_client import get_value
    lockdown = await get_value("talos:security:lockdown")
    if lockdown and lockdown.get("active"):
        return {
            "correlation_id": correlation_id,
            "blocked": True,
            "reason": "system_lockdown",
            "response": "System is in lockdown mode. Please provide unlock code to administrator.",
        }

    # Step 3: Retrieve RAG context
    try:
        from memory.rag import retrieve_and_format
        context_block = await retrieve_and_format(user_input)
    except Exception as exc:
        logger.warning("[%s] RAG retrieval failed (continuing without context): %s", correlation_id, exc)
        context_block = ""

    # Step 4: Build prompt with context
    prompt = user_input
    if context_block:
        prompt = f"{context_block}\n\n{user_input}"

    # Step 5: Route to model
    try:
        from intelligence.router import route
        response_text = await route(
            prompt=prompt,
            images=images,
            force_cloud=force_cloud,
        )
    except Exception as exc:
        logger.error("[%s] Model routing failed: %s", correlation_id, exc)
        return {
            "correlation_id": correlation_id,
            "error": str(exc),
            "response": None,
        }

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info("[%s] Response generated in %dms", correlation_id, duration_ms)

    # Step 6: Store conversation turn in vector memory
    asyncio.create_task(
        _store_turn(session_id, user_input, response_text, correlation_id)
    )

    return {
        "correlation_id": correlation_id,
        "session_id": session_id,
        "response": response_text,
        "duration_ms": duration_ms,
        "blocked": False,
    }


async def _store_turn(
    session_id: str,
    user_input: str,
    response: str,
    correlation_id: str,
) -> None:
    """Store conversation turn into ChromaDB for future RAG retrieval."""
    try:
        import time as _time
        from memory.rag import embed
        from memory.chroma_client import add_documents

        doc = f"User: {user_input}\nAssistant: {response}"
        embedding = embed([doc])[0]
        now = _time.time()

        await add_documents(
            collection_name="conversation_history",
            ids=[correlation_id],
            documents=[doc],
            embeddings=[embedding],
            metadatas=[{
                "session_id": session_id,
                "created_at": now,
                "last_access": now,
                "access_count": 1,
                "priority": "normal",
            }],
        )
    except Exception as exc:
        logger.warning("Failed to store conversation turn: %s", exc)
