"""
Phase 4 test — no API key needed, runs entirely locally.

Run with:  python -m tests.test_phase4_dedup

First run will be slow-ish (downloads the embedding model, a few hundred
MB, one time only). After that it's fast.

This works on whatever articles Phase 3 already stored in your database.
"""

from database.db import init_db, get_session
from database.models import SourceArticle
from services.dedup_service import ensure_embeddings_and_cluster
from services.relevance_service import filter_relevant_article_ids, score_relevance_for_articles


def run():
    print("Initializing database (safe to run even if already set up)...")
    init_db()

    with get_session() as session:
        all_ids = [row.id for row in session.query(SourceArticle.id).all()]

    if not all_ids:
        print("No articles found — run 'python -m tests.test_phase3_research' first.")
        return

    print(f"Found {len(all_ids)} articles in the database.")
    print("Computing embeddings (first run downloads the model, be patient)...")
    clusters = ensure_embeddings_and_cluster(all_ids)
    print(f"Grouped into {len(clusters)} story cluster(s).\n")

    print("Filtering by relevance to the configured niche...")
    relevant_ids = filter_relevant_article_ids(all_ids)
    print(f"{len(relevant_ids)} of {len(all_ids)} articles passed the relevance filter.\n")

    print("Every article's actual relevance score (highest to lowest) —")
    print("use this to sanity-check RELEVANCE_MIN_THRESHOLD in config.py:\n")
    scored = score_relevance_for_articles(all_ids)
    for item in scored:
        mark = "PASS" if item["passes"] else "drop"
        print(f"  [{mark}] {item['relevance']:.3f}  [{item['source_name']}] {item['title']}")
    print()

    with get_session() as session:
        print("Clusters with more than one article (corroborated stories):")
        found_multi = False
        for cluster_id, member_ids in clusters.items():
            if len(member_ids) > 1:
                found_multi = True
                print(f"\n  Cluster {cluster_id[:8]}... ({len(member_ids)} sources):")
                members = (
                    session.query(SourceArticle)
                    .filter(SourceArticle.id.in_(member_ids))
                    .all()
                )
                for m in members:
                    print(f"    - [{m.source_name}] {m.title}")
        if not found_multi:
            print("  (none found this run — that's fine, it depends on what's currently in the news)")


if __name__ == "__main__":
    run()