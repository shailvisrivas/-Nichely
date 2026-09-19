"""
Relevance filtering — Phase 4.

Deterministic filter: computes similarity between each article's embedding
and a fixed "niche description" embedding, drops anything below the
configured threshold. This runs after clustering-worthy embeddings exist,
and before topic scoring (Phase 5) ever sees an article.
"""

from functools import lru_cache

from config import NICHE_DESCRIPTION, RELEVANCE_MIN_THRESHOLD
from database.db import get_session
from database.models import SourceArticle
from services.embedding_service import embed_text, embedding_from_json, cosine_similarity


@lru_cache(maxsize=1)
def get_niche_embedding():
    return embed_text(NICHE_DESCRIPTION)


def compute_relevance(article_embedding_json: str) -> float:
    import numpy as np

    niche_vector = np.array(get_niche_embedding(), dtype="float32")
    article_vector = embedding_from_json(article_embedding_json)
    return cosine_similarity(article_vector, niche_vector)


def score_relevance_for_articles(article_ids: list[str]) -> list[dict]:
    """Returns every article's relevance score (not just the ones that
    pass), so you can inspect the actual numbers instead of only a
    pass/fail count. Useful for calibrating RELEVANCE_MIN_THRESHOLD and
    for demonstrating that filtering is transparent, not a black box."""
    results = []
    with get_session() as session:
        articles = (
            session.query(SourceArticle)
            .filter(SourceArticle.id.in_(article_ids))
            .filter(SourceArticle.embedding.isnot(None))
            .all()
        )
        for article in articles:
            relevance = compute_relevance(article.embedding)
            results.append(
                {
                    "id": article.id,
                    "title": article.title,
                    "source_name": article.source_name,
                    "relevance": relevance,
                    "passes": relevance >= RELEVANCE_MIN_THRESHOLD,
                }
            )
    return sorted(results, key=lambda r: r["relevance"], reverse=True)


def filter_relevant_article_ids(article_ids: list[str]) -> list[str]:
    """Returns only the article IDs that pass the relevance threshold.
    Articles with no embedding yet are skipped (call ensure_embeddings()
    from dedup_service first)."""
    kept = []
    with get_session() as session:
        articles = (
            session.query(SourceArticle)
            .filter(SourceArticle.id.in_(article_ids))
            .filter(SourceArticle.embedding.isnot(None))
            .all()
        )
        for article in articles:
            relevance = compute_relevance(article.embedding)
            if relevance >= RELEVANCE_MIN_THRESHOLD:
                kept.append(article.id)

    return kept