"""
SQLAlchemy models — one class per table in the locked spec (§11).

Design note: embeddings are stored as JSON-serialized float lists in a
Text column rather than a dedicated vector type. At this project's scale
(dozens of articles per run, hundreds of posts over a semester) a plain
column plus numpy cosine similarity at query time is simpler and fast
enough — no vector database needed. See utils/scoring.py and
services/embedding_service.py for how these are read back out.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceArticle(Base):
    __tablename__ = "source_articles"

    id = Column(String, primary_key=True, default=new_id)
    title = Column(Text, nullable=False)
    body_text = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    source_name = Column(String, nullable=False)
    reliability_tier = Column(Float, nullable=False)
    published_at = Column(String, nullable=False)  # ISO timestamp
    fetched_at = Column(String, nullable=False, default=now_iso)
    embedding = Column(Text)  # JSON-serialized float list
    story_cluster_id = Column(String)  # groups corroborating articles


class TopicConsidered(Base):
    __tablename__ = "topics_considered"

    id = Column(String, primary_key=True, default=new_id)  # = story_cluster_id for the run
    run_id = Column(String, nullable=False)
    headline_candidate = Column(Text, nullable=False)
    source_article_ids = Column(Text, nullable=False)  # JSON array of SourceArticle.id
    score_recency = Column(Float)
    score_relevance = Column(Float)
    score_reliability = Column(Float)
    score_novelty = Column(Float)
    score_audience = Column(Float)
    final_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # selected | shortlisted | rejected
    rejection_reason = Column(Text)
    reasoning_text = Column(Text)
    created_at = Column(String, nullable=False, default=now_iso)


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=new_id)
    topic_id = Column(String, nullable=False)  # FK -> topics_considered.id
    headline = Column(Text, nullable=False)
    caption = Column(Text, nullable=False)
    hashtags = Column(Text, nullable=False)  # JSON array
    cta = Column(Text)
    source_attribution = Column(Text)  # JSON array
    poster_local_path = Column(Text)
    poster_image_description = Column(Text)  # what the poster image should show (Phase 6/7)
    person_name = Column(Text)  # main public figure named in the article, if any (Phase 6/7)
    image_attribution = Column(Text)  # credit line for the poster photo, e.g. Wikimedia Commons (Phase 7)
    poster_public_url = Column(Text)
    carousel_slides_json = Column(Text)  # JSON array of short slide texts (carousel feature)
    poster_local_paths = Column(Text)    # JSON array of local paths, for carousel posts
    poster_public_urls = Column(Text)    # JSON array of public URLs, for carousel posts
    approval_status = Column(String, nullable=False, default="pending")  # pending|approved|rejected
    publish_mode = Column(String, nullable=False)  # mock | live
    ig_media_id = Column(String)  # null until published
    published_at = Column(String)
    created_at = Column(String, nullable=False, default=now_iso)


class EngagementSnapshot(Base):
    __tablename__ = "engagement_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    post_id = Column(String, nullable=False)  # FK -> posts.id
    fetched_at = Column(String, nullable=False, default=now_iso)
    reach = Column(Integer)
    impressions = Column(Integer)
    likes = Column(Integer)
    comments = Column(Integer)
    saves = Column(Integer)
    shares = Column(Integer)
    profile_visits = Column(Integer)


class ScoringWeights(Base):
    __tablename__ = "scoring_weights"

    id = Column(String, primary_key=True, default=new_id)
    w_recency = Column(Float, nullable=False)
    w_relevance = Column(Float, nullable=False)
    w_reliability = Column(Float, nullable=False)
    w_novelty = Column(Float, nullable=False)
    w_audience = Column(Float, nullable=False)
    change_log = Column(Text)  # human-readable reason for this version
    active = Column(Integer, nullable=False, default=1)  # 1 = current, 0 = historical
    created_at = Column(String, nullable=False, default=now_iso)