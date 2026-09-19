"""
Deduplication / clustering service — Phase 4.

Groups articles that are about the same underlying story (like multiple
outlets covering the same product launch) into "story clusters", so
downstream scoring treats them as one topic candidate with N corroborating
sources — rather than N separate, competing topics.

Algorithm (deliberately simple — see spec §6/§7 for why no vector DB or
heavier clustering library is needed at this scale):
1. Compute (or reuse) an embedding for every article that doesn't have one yet.
2. Greedily group articles: for each article, if its embedding is above
   the similarity threshold against any article already in an existing
   cluster, join that cluster; otherwise start a new one.
3. Write the resulting story_cluster_id back onto each article.

This is O(n^2) in the number of articles being clustered, which is
completely fine at this project's scale (tens of articles per run).
"""

import uuid

import numpy as np

from config import DEDUP_SIMILARITY_THRESHOLD
from database.db import get_session
from database.models import SourceArticle
from services.embedding_service import embed_text, embedding_to_json, embedding_from_json, cosine_similarity


def ensure_embeddings(article_ids: list[str] | None = None) -> int:
    """Computes and stores embeddings for any articles that don't have
    one yet. If article_ids is given, only considers those; otherwise
    considers every article missing an embedding. Returns count embedded."""
    embedded_count = 0
    with get_session() as session:
        query = session.query(SourceArticle).filter(SourceArticle.embedding.is_(None))
        if article_ids is not None:
            query = query.filter(SourceArticle.id.in_(article_ids))

        for article in query.all():
            text_for_embedding = f"{article.title}. {article.body_text}"
            vector = embed_text(text_for_embedding)
            article.embedding = embedding_to_json(vector)
            embedded_count += 1

    return embedded_count


def cluster_articles(article_ids: list[str]) -> dict[str, list[str]]:
    """Groups the given articles into story clusters. Returns a dict of
    {story_cluster_id: [article_id, ...]}. Also writes story_cluster_id
    back onto each SourceArticle row.

    Call ensure_embeddings() first (or this will skip articles with no
    embedding yet).
    """
    with get_session() as session:
        articles = (
            session.query(SourceArticle)
            .filter(SourceArticle.id.in_(article_ids))
            .filter(SourceArticle.embedding.isnot(None))
            .all()
        )

        # (article_id, vector) pairs, plus which cluster each currently belongs to
        vectors: dict[str, np.ndarray] = {
            a.id: embedding_from_json(a.embedding) for a in articles
        }
        cluster_of: dict[str, str] = {}
        clusters: dict[str, list[str]] = {}

        for article in articles:
            this_vector = vectors[article.id]
            matched_cluster_id = None

            # compare against one representative (the first member) of each
            # existing cluster — good enough at this scale, avoids O(n^2)
            # blowing up in a way that matters
            for cluster_id, member_ids in clusters.items():
                representative_vector = vectors[member_ids[0]]
                similarity = cosine_similarity(this_vector, representative_vector)
                if similarity >= DEDUP_SIMILARITY_THRESHOLD:
                    matched_cluster_id = cluster_id
                    break

            if matched_cluster_id is None:
                matched_cluster_id = str(uuid.uuid4())
                clusters[matched_cluster_id] = []

            clusters[matched_cluster_id].append(article.id)
            cluster_of[article.id] = matched_cluster_id

        # write cluster assignments back to the database
        for article in articles:
            article.story_cluster_id = cluster_of[article.id]

    return clusters


def ensure_embeddings_and_cluster(article_ids: list[str]) -> dict[str, list[str]]:
    """Convenience entrypoint: embed anything missing, then cluster."""
    ensure_embeddings(article_ids)
    return cluster_articles(article_ids)
