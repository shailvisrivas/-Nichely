"""
Engine/session setup for Nichely's SQLite database.

Usage:
    from database.db import get_session, init_db
    init_db()  # run once, creates tables if they don't exist
    with get_session() as session:
        ...
"""

from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL, DEFAULT_SCORING_WEIGHTS
from database.models import Base, ScoringWeights, EngagementSnapshot

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    """Create all tables if they don't already exist, and seed default
    scoring weights if no active weight row exists yet."""
    Base.metadata.create_all(engine)
    _seed_default_weights_if_missing()


def _seed_default_weights_if_missing():
    with get_session() as session:
        existing = session.execute(
            select(ScoringWeights).where(ScoringWeights.active == 1)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ScoringWeights(
                    w_recency=DEFAULT_SCORING_WEIGHTS["w_recency"],
                    w_relevance=DEFAULT_SCORING_WEIGHTS["w_relevance"],
                    w_reliability=DEFAULT_SCORING_WEIGHTS["w_reliability"],
                    w_novelty=DEFAULT_SCORING_WEIGHTS["w_novelty"],
                    w_audience=DEFAULT_SCORING_WEIGHTS["w_audience"],
                    change_log="Initial default weights (seeded at first run).",
                    active=1,
                )
            )
            session.commit()


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_active_weights():
    """Returns the current active ScoringWeights row."""
    with get_session() as session:
        weights = session.execute(
            select(ScoringWeights).where(ScoringWeights.active == 1)
        ).scalar_one_or_none()
        if weights is None:
            raise RuntimeError("No active scoring weights found — did you run init_db()?")
        # detach values we need before the session closes
        return {
            "w_recency": weights.w_recency,
            "w_relevance": weights.w_relevance,
            "w_reliability": weights.w_reliability,
            "w_novelty": weights.w_novelty,
            "w_audience": weights.w_audience,
        }


# ---------------------------------------------------------------------
# Phase 10/11 helpers — engagement snapshots + scoring-weight rotation
# ---------------------------------------------------------------------

def save_engagement_snapshot(post_id: str, analytics: dict) -> str:
    """Persists one Phase 10 analytics read as an EngagementSnapshot row
    tied to the given post. Returns the new snapshot's id."""
    with get_session() as session:
        snapshot = EngagementSnapshot(
            post_id=post_id,
            reach=analytics.get("reach"),
            impressions=analytics.get("impressions"),
            likes=analytics.get("likes"),
            comments=analytics.get("comments"),
            saves=analytics.get("saves"),
            shares=analytics.get("shares"),
            profile_visits=analytics.get("profile_visits"),
        )
        session.add(snapshot)
        session.flush()
        return snapshot.id


def get_latest_snapshot_for_post(post_id: str) -> dict | None:
    """Returns the most recent EngagementSnapshot for a post as a plain
    dict shaped like Phase 10's analytics dict, or None if there isn't one."""
    with get_session() as session:
        snap = (
            session.query(EngagementSnapshot)
            .filter(EngagementSnapshot.post_id == post_id)
            .order_by(EngagementSnapshot.fetched_at.desc())
            .first()
        )
        if snap is None:
            return None

        reach = snap.reach or 0
        engagement_rate = 0.0
        if reach > 0:
            engagement_rate = (
                (snap.likes or 0) + (snap.comments or 0) + (snap.saves or 0) + (snap.shares or 0)
            ) / reach

        return {
            "media_id": None,
            "likes": snap.likes or 0,
            "comments": snap.comments or 0,
            "reach": reach,
            "saves": snap.saves or 0,
            "shares": snap.shares or 0,
            "engagement_rate": round(engagement_rate, 4),
            "fetched_at": snap.fetched_at,
        }


def rotate_active_weights(new_weights: dict, change_log: str) -> None:
    """Phase 11: deactivates the current ScoringWeights row and inserts
    the newly-optimized weights as the new active row. Keeps history
    instead of overwriting, so you can show a weight-change timeline."""
    with get_session() as session:
        session.query(ScoringWeights).filter(ScoringWeights.active == 1).update(
            {"active": 0}
        )
        session.add(
            ScoringWeights(
                w_recency=new_weights["w_recency"],
                w_relevance=new_weights["w_relevance"],
                w_reliability=new_weights["w_reliability"],
                w_novelty=new_weights["w_novelty"],
                w_audience=new_weights["w_audience"],
                change_log=change_log,
                active=1,
            )
        )
