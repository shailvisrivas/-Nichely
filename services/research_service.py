"""
Research service — Phase 3.

Fetches current articles for the configured niche from NewsAPI.org,
cleans the text, tags each article's source reliability, and stores
new articles in the source_articles table (skipping ones already
stored by URL, so re-running this doesn't create duplicates).

This is a deterministic service, not an agent (see spec §4/§9): it
makes no judgement calls, it just fetches and stores.

NewsAPI free-tier notes (verified at build time, worth knowing):
- Free "Developer" plan only allows requests that originate from
  localhost — fine for building/demoing on your own machine, not for
  a deployed server.
- Free plan is rate-limited to 100 requests/day — this service batches
  all niche keywords into as few calls as practical to stay well under that.
- Free plan also only returns articles from roughly the last month, and
  the results themselves are already fresh/sorted-by-recency, so no
  special handling is needed there.
"""

import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

from config import (
    NICHE_SEARCH_KEYWORDS,
    MAX_ARTICLE_AGE_HOURS,
    SOURCE_RELIABILITY_TIERS,
    TRUSTED_DOMAINS_MIN_TIER,
)
from database.db import get_session
from database.models import SourceArticle
from services.reliability_service import get_reliability_tier
from utils.text_cleaning import clean_article_text

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"

# Built once from config's allowlist — only domains at/above this
# reliability tier are asked for at fetch time.
TRUSTED_DOMAINS = ",".join(
    domain
    for domain, tier in SOURCE_RELIABILITY_TIERS.items()
    if tier >= TRUSTED_DOMAINS_MIN_TIER
)


def fetch_raw_articles(page_size: int = 20) -> list[dict]:
    """Calls NewsAPI once per niche keyword and returns the combined,
    raw article dicts exactly as NewsAPI returns them (deduped by URL
    within this fetch, before any DB interaction)."""
    if not NEWS_API_KEY:
        raise RuntimeError(
            "NEWS_API_KEY is not set. Add it to your .env file before running this."
        )

    since = (datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    seen_urls = set()
    combined = []

    for keyword in NICHE_SEARCH_KEYWORDS:
        params = {
            "q": keyword,
            "language": "en",
            "sortBy": "publishedAt",
            "from": since,
            "pageSize": page_size,
            "domains": TRUSTED_DOMAINS,  # only fetch from allowlisted tech outlets
            "apiKey": NEWS_API_KEY,
        }
        response = requests.get(NEWS_API_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "ok":
            raise RuntimeError(f"NewsAPI returned an error for '{keyword}': {payload}")

        for article in payload.get("articles", []):
            url = article.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined.append(article)

    return combined


def store_new_articles(raw_articles: list[dict]) -> int:
    """Cleans and stores articles that aren't already in the database
    (by URL). Returns the number of NEW articles actually stored."""
    stored_count = 0

    with get_session() as session:
        existing_urls = {row.url for row in session.query(SourceArticle.url).all()}

        for article in raw_articles:
            url = article.get("url")
            if not url or url in existing_urls:
                continue  # already have it, skip

            title = article.get("title") or "(no title)"
            body_source = article.get("content") or article.get("description") or ""
            body_text = clean_article_text(body_source)
            source_name = (article.get("source") or {}).get("name") or "unknown"
            published_at = article.get("publishedAt") or datetime.now(timezone.utc).isoformat()
            reliability_tier = get_reliability_tier(url)

            session.add(
                SourceArticle(
                    title=title,
                    body_text=body_text,
                    url=url,
                    source_name=source_name,
                    reliability_tier=reliability_tier,
                    published_at=published_at,
                )
            )
            existing_urls.add(url)
            stored_count += 1

    return stored_count


def run_research_pipeline() -> int:
    """Full Phase 3 entrypoint: fetch, then store. Returns count of new
    articles stored."""
    raw_articles = fetch_raw_articles()
    return store_new_articles(raw_articles)


if __name__ == "__main__":
    new_count = run_research_pipeline()
    print(f"Fetched and stored {new_count} new article(s).")
