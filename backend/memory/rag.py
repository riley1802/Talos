"""RAG — Retrieval-Augmented Generation pipeline.

Scoring formula (spec § 3.2):
    retention_score = recency * 0.3 + frequency * 0.3 + priority * 0.4
"""
import logging
import os
import time
from typing import Optional

from sentence_transformers import SentenceTransformer

from memory.chroma_client import query, enforce_vector_ceiling

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
SIMILARITY_THRESHOLD = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.75"))
CONTEXT_TOP_N = int(os.getenv("MEMORY_CONTEXT_WINDOW", "10"))

_embedder: Optional[SentenceTransformer] = None

PRIORITY_SCORES = {"critical": 1.0, "high": 0.8, "normal": 0.5, "temporary": 0.2}


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    return model.encode(texts, normalize_embeddings=True).tolist()


def _score_result(metadata: dict) -> float:
    now = time.time()
    last_access = metadata.get("last_access", now)
    created_at = metadata.get("created_at", now)
    access_count = int(metadata.get("access_count", 1))
    priority = metadata.get("priority", "normal")

    age_days = max((now - created_at) / 86400, 0.01)
    recency = 1.0 / (1.0 + age_days / 30)

    frequency = min(access_count / 10.0, 1.0)

    priority_val = PRIORITY_SCORES.get(priority, 0.5)

    return recency * 0.3 + frequency * 0.3 + priority_val * 0.4


async def retrieve(
    query_text: str,
    collections: Optional[list[str]] = None,
    n_per_collection: int = 5,
) -> list[dict]:
    if collections is None:
        collections = ["conversation_history", "knowledge_base", "skill_memory"]

    query_embedding = embed([query_text])[0]
    candidates = []

    for col_name in collections:
        try:
            results = await query(
                collection_name=col_name,
                query_embeddings=[query_embedding],
                n_results=n_per_collection,
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, distances):
                similarity = 1.0 - dist  # cosine: distance → similarity
                if similarity < SIMILARITY_THRESHOLD:
                    continue
                score = _score_result(meta)
                candidates.append({
                    "document": doc,
                    "metadata": meta,
                    "similarity": similarity,
                    "score": score,
                    "collection": col_name,
                })
        except Exception as exc:
            logger.warning("RAG retrieve error in %s: %s", col_name, exc)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:CONTEXT_TOP_N]


def build_context_block(retrieved: list[dict]) -> str:
    if not retrieved:
        return ""
    parts = ["[MEMORY CONTEXT]"]
    for item in retrieved:
        col = item["collection"]
        doc = item["document"]
        score = item["score"]
        parts.append(f"[{col} | score={score:.2f}] {doc}")
    parts.append("[END CONTEXT]")
    return "\n".join(parts)


async def retrieve_and_format(query_text: str) -> str:
    await enforce_vector_ceiling()
    retrieved = await retrieve(query_text)
    return build_context_block(retrieved)
