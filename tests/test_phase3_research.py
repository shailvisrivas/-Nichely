"""
Phase 3 test — requires a real NEWS_API_KEY in your .env file.

Run with:  python -m tests.test_phase3_research

This calls the real NewsAPI, so it will use a small amount of your
daily free-tier quota (a handful of requests — one per niche keyword
in config.py).
"""

from database.db import init_db, get_session
from database.models import SourceArticle
from services.research_service import run_research_pipeline


def run():
    print("Initializing database (safe to run even if already set up)...")
    init_db()

    print("Fetching current articles from NewsAPI for your configured niche...")
    new_count = run_research_pipeline()
    print(f"Stored {new_count} new article(s).\n")

    print("Here's what's in the database now (most recent 10):")
    with get_session() as session:
        articles = (
            session.query(SourceArticle)
            .order_by(SourceArticle.fetched_at.desc())
            .limit(10)
            .all()
        )
        if not articles:
            print("  (no articles found — check your NEWS_API_KEY and niche keywords)")
        for a in articles:
            print(f"  - [{a.source_name}] (reliability={a.reliability_tier}) {a.title}")
            print(f"      {a.url}")


if __name__ == "__main__":
    run()
