"""ChromaDB client — long-term vector memory (100K vectors max)."""
import asyncio
import logging
import os
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMADB_MAX_VECTORS = int(os.getenv("CHROMADB_MAX_VECTORS", "100000"))
PRUNE_THRESHOLD = 90000  # Start pruning at 90K vectors

COLLECTION_NAMES = [
    "skill_memory",
    "conversation_history",
    "knowledge_base",
    "skill_registry",
]

_client: Optional[chromadb.AsyncHttpClient] = None


async def get_client() -> chromadb.AsyncHttpClient:
    global _client
    if _client is None:
        _client = await chromadb.AsyncHttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


async def init_collections() -> None:
    client = await get_client()
    for name in COLLECTION_NAMES:
        try:
            await client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Collection ready: %s", name)
        except Exception as exc:
            logger.error("Failed to init collection %s: %s", name, exc)
            raise


async def get_collection(name: str):
    client = await get_client()
    return await client.get_collection(name)


async def add_documents(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: Optional[list[dict]] = None,
) -> None:
    col = await get_collection(collection_name)
    await col.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas or [{} for _ in ids],
    )


async def query(
    collection_name: str,
    query_embeddings: list[list[float]],
    n_results: int = 5,
    where: Optional[dict] = None,
) -> dict:
    col = await get_collection(collection_name)
    kwargs = {"query_embeddings": query_embeddings, "n_results": n_results}
    if where:
        kwargs["where"] = where
    return await col.query(**kwargs)


async def get_total_vector_count() -> int:
    client = await get_client()
    total = 0
    for name in COLLECTION_NAMES:
        try:
            col = await client.get_collection(name)
            total += await col.count()
        except Exception:
            pass
    return total


async def prune_old_vectors(collection_name: str, max_to_remove: int = 5000) -> int:
    """Remove oldest temporary vectors when approaching the 90K limit."""
    col = await get_collection(collection_name)
    results = await col.get(
        where={"priority": {"$eq": "temporary"}},
        include=["metadatas"],
        limit=max_to_remove,
    )
    ids_to_remove = results.get("ids", [])
    if ids_to_remove:
        await col.delete(ids=ids_to_remove)
        logger.info("Pruned %d vectors from %s", len(ids_to_remove), collection_name)
    return len(ids_to_remove)


async def enforce_vector_ceiling() -> None:
    total = await get_total_vector_count()
    if total >= PRUNE_THRESHOLD:
        logger.warning("Vector count %d >= threshold %d, pruning...", total, PRUNE_THRESHOLD)
        for name in COLLECTION_NAMES:
            await prune_old_vectors(name, max_to_remove=1000)


async def ping() -> bool:
    try:
        client = await get_client()
        await client.heartbeat()
        return True
    except Exception as exc:
        logger.error("ChromaDB ping failed: %s", exc)
        return False


async def wait_for_chromadb(retries: int = 15, delay: float = 1.0) -> bool:
    for attempt in range(1, retries + 1):
        if await ping():
            logger.info("ChromaDB connected (attempt %d)", attempt)
            return True
        logger.warning("ChromaDB not ready, attempt %d/%d", attempt, retries)
        await asyncio.sleep(delay)
    logger.error("ChromaDB failed to connect after %d attempts", retries)
    return False
