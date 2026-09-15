"""RAG retrieval over the semantic catalog: embeds SEMANTIC_CATALOG entries and incoming
questions with the Gemini embedding API, ranks by cosine similarity, and returns only the
entries relevant to a given question for prompt injection (calendar_api/views.py).

Falls back to the full static catalog on any embedding failure (missing API key, network
error, quota) so the chat pipeline never breaks on this step, consistent with the existing
LLM cascade's graceful-degradation design (llm_router.py).
"""
import logging

import numpy as np
from django.conf import settings
from google import genai
from google.genai import types

from .semantic_catalog import SEMANTIC_CATALOG

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

_catalog_embedding_cache = None  # process-lifetime cache; catalog is static


def _embed(texts, task_type):
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    return [np.array(e.values, dtype=float) for e in result.embeddings]


def _get_catalog_embeddings():
    global _catalog_embedding_cache
    if _catalog_embedding_cache is None:
        keys = list(SEMANTIC_CATALOG.keys())
        texts = [
            f"{spec['display_name']}: {spec['description']} (aliases: {', '.join(spec['aliases'])})"
            for spec in SEMANTIC_CATALOG.values()
        ]
        _catalog_embedding_cache = list(zip(keys, _embed(texts, "RETRIEVAL_DOCUMENT")))
    return _catalog_embedding_cache


def _cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def retrieve_relevant_catalog_entries(question: str, top_k: int = 2, min_similarity: float = 0.5) -> dict:
    """Embeds `question`, ranks SEMANTIC_CATALOG entries by cosine similarity against their
    precomputed embeddings, and returns the top_k entries scoring at or above min_similarity
    as a {key: spec} dict. Returns the FULL catalog if nothing clears the similarity floor,
    or if embedding fails for any reason (no GEMINI_API_KEY, network error, quota, etc.) --
    the caller's prompt-building should never break because retrieval had a bad day.
    """
    try:
        catalog_vecs = _get_catalog_embeddings()
        [question_vec] = _embed([question], "RETRIEVAL_QUERY")
        ranked = sorted(
            ((key, _cosine(question_vec, vec)) for key, vec in catalog_vecs),
            key=lambda kv: kv[1],
            reverse=True,
        )
        matched_keys = [key for key, score in ranked[:top_k] if score >= min_similarity]
        return {key: SEMANTIC_CATALOG[key] for key in matched_keys} or SEMANTIC_CATALOG
    except Exception as exc:
        logger.warning("RAG retrieval failed, falling back to full catalog: %s", exc)
        return SEMANTIC_CATALOG
