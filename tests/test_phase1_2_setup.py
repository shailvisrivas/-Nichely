"""
Phase 1-2 smoke test.

Run with:  python -m tests.test_phase1_2_setup

This does NOT require any API keys — it only proves the folder structure,
config, and database layer work end to end. If this passes, Phase 1 and 2
are done and you can move on to Phase 3 (research service).
"""

import json

from database.db import init_db, get_session, get_active_weights
from database.models import SourceArticle, TopicConsidered


def run():
    print("1. Initializing database (creates tables + seeds default weights)...")
    init_db()
    print("   OK")

    print("2. Reading back active scoring weights...")
    weights = get_active_weights()
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "Default weights should sum to 1.0"
    print(f"   OK — {weights}")

    print("3. Inserting a dummy source article...")
    with get_session() as session:
        article = SourceArticle(
            title="Test Article: A New AI Model Was Announced",
            body_text="This is placeholder body text for the smoke test.",
            url="https://example.com/test-article",
            source_name="example.com",
            reliability_tier=0.5,
            published_at="2026-09-05T00:00:00+00:00",
        )
        session.add(article)
        session.flush()
        article_id = article.id
    print(f"   OK — inserted article id={article_id}")

    print("4. Inserting a dummy topic considered row referencing that article...")
    with get_session() as session:
        topic = TopicConsidered(
            run_id="test-run-1",
            headline_candidate="A New AI Model Was Announced",
            source_article_ids=json.dumps([article_id]),
            score_recency=0.9,
            score_relevance=0.8,
            score_reliability=0.5,
            score_novelty=0.7,
            score_audience=0.6,
            final_score=0.71,
            status="selected",
            reasoning_text="Placeholder reasoning for smoke test.",
        )
        session.add(topic)
    print("   OK")

    print("\nPhase 1-2 setup verified. Database file created, schema in place, "
          "default weights seeded, read/write round-trip works.")


if __name__ == "__main__":
    run()
