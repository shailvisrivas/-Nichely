"""
Central configuration for Nichely.

Everything a non-code-change tweak would touch lives here: the niche
definition, scoring thresholds, and the source reliability allowlist.
Keeping these out of the agent/service code means you can retune the
system without touching logic — worth mentioning in your report as a
deliberate separation of config from code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---- Niche configuration (MVP: single niche) ----
NICHE_NAME = "Bollywood & Hollywood Entertainment News"
NICHE_DESCRIPTION = (
    "Current news, film/show announcements, casting updates, box office "
    "results, trailers, award-season coverage, and celebrity news spanning "
    "both Bollywood and Hollywood, relevant to a general entertainment-"
    "interested audience."
)
NICHE_SEARCH_KEYWORDS = [
    "Bollywood",
    "Hollywood movie",
    "box office collection",
    "film trailer release",
    "celebrity news",
    "movie casting announcement",
    "red carpet event",
    "78th Primetime Emmy Awards",
]

# Only articles from these domains are fetched (built from the allowlist
# below, tier >= 0.8) — this is a first, cheap filter that runs at fetch
# time, on top of the keyword search. Full relevance/novelty scoring still
# happens in Phase 4; this just stops obviously off-topic sources from
# ever entering the database in the first place.
TRUSTED_DOMAINS_MIN_TIER = 0.8

# ---- Research pipeline thresholds ----
MAX_ARTICLE_AGE_HOURS = 168  # TEMP for testing — revert before final demo!         
DEDUP_SIMILARITY_THRESHOLD = 0.85   # cosine similarity above this = same story cluster
RELEVANCE_MIN_THRESHOLD = 0.18
# Note: all-MiniLM-L6-v2 (our embedding model) tends to produce lower raw
# cosine similarity scores than intuition suggests, even for clearly related
# text — 0.18-0.35 is a normal range for "genuinely on-topic." This value
# was tuned by inspecting real scores (see test_phase4_dedup.py's printout),
# not guessed — worth documenting in your report as a legitimate calibration step.     # cosine similarity below this = filtered out entirely

# ---- Source reliability allowlist ----
# tier: 1.0 = established/primary entertainment outlets, 0.6 = aggregator/
# blog-tier, 0.3 = unknown/unlisted fallback. Extend this list as you find
# more sources for either industry.
SOURCE_RELIABILITY_TIERS = {
    # Hollywood / international
    "variety.com": 1.0,
    "hollywoodreporter.com": 1.0,
    "deadline.com": 1.0,
    "ew.com": 0.9,
    "people.com": 0.8,
    # Bollywood / Indian entertainment
    "bollywoodhungama.com": 1.0,
    "pinkvilla.com": 0.9,
    "filmfare.com": 0.9,
    "indianexpress.com": 0.9,
    "hindustantimes.com": 0.9,
    # General aggregator-tier fallback
    "medium.com": 0.5,
}
DEFAULT_RELIABILITY_TIER = 0.3  # any source not in the dict above

# ---- Default scoring weights (Feedback Agent adjusts these over time) ----
DEFAULT_SCORING_WEIGHTS = {
    "w_recency": 0.25,
    "w_relevance": 0.25,
    "w_reliability": 0.20,
    "w_novelty": 0.15,
    "w_audience": 0.15,
}

# ---- Embedding model ----
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # local sentence-transformers model, no API cost

# ---- LLM provider (Phase 5 & 6) ----
GEMINI_MODEL_NAME = "gemini-3.6-flash"  # cheap/free-tier friendly model for scoring + captioning
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---- Poster settings ----
POSTER_WIDTH = 1080
POSTER_HEIGHT = 1080  # square for MVP
POSTER_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "generated_posters")
POSTER_SOURCE_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "data", "source_images")

# ---- Publishing ----
PUBLISH_MODE = os.getenv("PUBLISH_MODE", "mock")  # "mock" | "live"

# ---- Database ----
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nichely.db")