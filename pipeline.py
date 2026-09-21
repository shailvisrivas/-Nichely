"""
Pipeline orchestrator — Phases 12-15.

Ties together everything built in Phases 3-11 into one runnable cycle,
and adds the final pieces needed for a real, end-to-end, scheduled run:

    Phase 12 (scheduler integration): run_full_cycle() is the function
        the scheduler_service.NichelyScheduler actually calls on a
        timer — see start_scheduler() below and its use in app.py's
        sidebar.

    Phase 13 (real publish wiring): publish_approved_post() is what
        turns an approved Post row into a real (or mock) Instagram
        post, uploading the poster to public hosting first if needed.

    Phase 14 (live/production readiness): check_live_readiness()
        verifies every credential PUBLISH_MODE=live needs is present
        *before* you flip the switch, so the first live run doesn't
        fail halfway through.

    Phase 15 (final end-to-end run): run_full_cycle(auto_publish=True)
        chains research -> topic scoring -> content generation ->
        poster -> publish -> analytics -> feedback into one call, for
        the fully unattended path. The default (auto_publish=False) is
        what the scheduler should normally use: it stops right before
        publish, so a human still approves each post in app.py — that
        human-in-the-loop step is Nichely's actual design, not a gap.

Run a single cycle by hand with:
    python -m pipeline
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config import PUBLISH_MODE
from database.db import (
    get_session,
    get_active_weights,
    save_engagement_snapshot,
    get_latest_snapshot_for_post,
    rotate_active_weights,
)
from database.models import Post
from services.research_service import run_research_pipeline
from agents.topic_scout import run_topic_scout
from agents.content_strategist import run_content_strategist, get_selected_topic
from services.poster_service import generate_poster_for_latest_pending_post, ensure_public_url_for_post
from services.instagramservice import publish_post, get_publish_mode, InstagramPublishError
from services.analytics_service import get_post_analytics, AnalyticsError
from services.feedback_service import run_feedback_optimization
from services.scheduler_service import create_scheduler, NichelyScheduler


class PipelineError(RuntimeError):
    """Raised when a pipeline step fails in a way the caller should see."""


# ---------------------------------------------------------------------
# Phase 14 — live/production readiness check
# ---------------------------------------------------------------------

def check_live_readiness() -> dict:
    """Checks whether everything PUBLISH_MODE=live needs is actually in
    place, without publishing anything. Meant to be run once before
    switching the .env flag from mock to live, and surfaced in app.py's
    sidebar so it's visible at a glance.

    Returns a dict:
        {"ready": bool, "issues": [str, ...], "mode": "mock"|"live"}
    """
    import os

    issues = []

    for var in ("IG_APP_ID", "IG_APP_SECRET", "IG_ACCESS_TOKEN", "IG_USER_ID"):
        if not os.getenv(var):
            issues.append(f"{var} is not set in .env")

    if not os.getenv("CLOUDINARY_URL"):
        issues.append(
            "CLOUDINARY_URL is not set — live publishing needs a public "
            "image URL and can't use a local poster file path."
        )

    return {
        "ready": len(issues) == 0,
        "issues": issues,
        "mode": get_publish_mode(),
    }


# ---------------------------------------------------------------------
# Phase 13 — publish an already-approved post for real (or mock)
# ---------------------------------------------------------------------

def _build_caption_text(post: Post) -> str:
    hashtags = json.loads(post.hashtags) if post.hashtags else []
    hashtag_line = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    parts = [post.caption]
    if post.cta:
        parts.append(post.cta)
    if hashtag_line:
        parts.append(hashtag_line)
    return "\n\n".join(p for p in parts if p)


def publish_approved_post(post_id: str) -> dict:
    """Publishes a single approved post: uploads its poster to public
    hosting if needed (live mode only), calls the Instagram service, and
    writes the result (ig_media_id, published_at, publish_mode) back
    onto the Post row.

    Safe to call in either PUBLISH_MODE — in mock mode no public URL
    is required and nothing leaves the machine.
    """
    with get_session() as session:
        post = session.query(Post).filter(Post.id == post_id).one_or_none()
        if post is None:
            raise PipelineError(f"No post found with id {post_id}")
        if post.approval_status != "approved":
            raise PipelineError(
                f"Post {post_id} is '{post.approval_status}', not 'approved' — "
                "approve it in app.py before publishing."
            )
        caption_text = _build_caption_text(post)
        local_path = post.poster_local_path
        public_url = post.poster_public_url
        has_carousel = bool(post.poster_local_paths)

    mode = get_publish_mode()

    # Phase 16 (carousel feature) -- if this post has multiple slides
    # generated (poster_local_paths is set), publish it as a carousel
    # instead of a single image.
    if has_carousel:
        from services.poster_service import ensure_public_urls_for_carousel
        from services.instagramservice import publish_carousel_post

        if mode == "live":
            image_urls = ensure_public_urls_for_carousel(post_id)
        else:
            with get_session() as session:
                post = session.query(Post).filter(Post.id == post_id).one()
                image_urls = json.loads(post.poster_local_paths)

        result = publish_carousel_post(caption_text, image_urls)
    else:
        if mode == "live":
            if not public_url:
                public_url = ensure_public_url_for_post(post_id)
            image_url = public_url
        else:
            # Mock mode never contacts Instagram, so any non-empty string
            # satisfies validate_post() — prefer the public URL if it
            # already exists, else fall back to the local path.
            image_url = public_url or local_path or "mock://no-image"

        result = publish_post(caption_text, image_url)

    with get_session() as session:
        post = session.query(Post).filter(Post.id == post_id).one()
        post.publish_mode = result["mode"]
        post.ig_media_id = result.get("media_id") or f"mock_{post.id[:8]}"
        post.published_at = result["published_at"]

    return result


# ---------------------------------------------------------------------
# Phase 10/11 — refresh analytics + optimize weights for a published post
# ---------------------------------------------------------------------

def refresh_analytics_and_optimize(post_id: str) -> dict:
    """Fetches current Instagram analytics for a published post, saves
    them as a snapshot, and runs the Feedback Agent to roll the scoring
    weights forward. Returns a dict with both results so callers (the
    Streamlit UI, or the scheduler) can display what changed."""
    with get_session() as session:
        post = session.query(Post).filter(Post.id == post_id).one_or_none()
        if post is None:
            raise PipelineError(f"No post found with id {post_id}")
        if not post.ig_media_id:
            raise PipelineError(f"Post {post_id} has not been published yet.")
        media_id = post.ig_media_id

    try:
        analytics = get_post_analytics(media_id)
    except AnalyticsError as exc:
        raise PipelineError(f"Could not fetch analytics: {exc}") from exc

    save_engagement_snapshot(post_id, analytics)

    current_weights = get_active_weights()
    optimization = run_feedback_optimization(analytics, current_weights)
    rotate_active_weights(
        optimization["new_weights"],
        change_log=f"Auto-optimized from post {post_id[:8]} performance: {optimization['reasoning']}",
    )

    return {"analytics": analytics, "optimization": optimization}


# ---------------------------------------------------------------------
# Phase 4 glue — embed, relevance-filter and cluster newly fetched articles
# ---------------------------------------------------------------------

def prepare_articles_for_scout() -> dict:
    """Runs the Phase 4 steps that the Topic Scout depends on.

    The Topic Scout only looks at articles that already have a
    story_cluster_id, and that id is only ever written by the clustering
    step. Nothing else in the app called it, so every article fetched by a
    cycle stayed un-clustered and the Scout reported "No eligible candidate
    stories found". This function closes that gap:

        1. embed any article that has no embedding yet
        2. drop articles below RELEVANCE_MIN_THRESHOLD (they stay
           un-clustered, so they are simply ignored by the Scout)
        3. cluster the survivors into story clusters

    Only articles with no story_cluster_id yet are touched, so cluster ids
    that existing topics/posts already point at never change.
    """
    from database.models import SourceArticle
    from services.dedup_service import ensure_embeddings, cluster_articles
    from services.relevance_service import filter_relevant_article_ids

    with get_session() as session:
        pending_ids = [
            row.id
            for row in session.query(SourceArticle.id)
            .filter(SourceArticle.story_cluster_id.is_(None))
            .all()
        ]

    if not pending_ids:
        return {"pending": 0, "embedded": 0, "relevant": 0, "clusters": 0}

    embedded = ensure_embeddings(pending_ids)
    relevant_ids = filter_relevant_article_ids(pending_ids)
    clusters = cluster_articles(relevant_ids) if relevant_ids else {}

    return {
        "pending": len(pending_ids),
        "embedded": embedded,
        "relevant": len(relevant_ids),
        "clusters": len(clusters),
    }


# ---------------------------------------------------------------------
# Phase 12/15 — the full cycle
# ---------------------------------------------------------------------

def run_full_cycle(auto_publish: bool = False, run_feedback_for_recent: bool = True) -> dict:
    """Runs one complete Nichely cycle:

        1. Research  (Phase 3)   — fetch fresh articles
        2. Topic Scout (Phase 4/5) — embed + relevance-filter + cluster the
           new articles, then score, rank and pick a topic
        3. Content Strategist (Phase 6) — write caption/hashtags/CTA
        4. Poster (Phase 7)      — render the poster image
        5. Publish (Phase 9/13)  — ONLY if auto_publish=True; otherwise
           the post is left 'pending' for human approval in app.py,
           which is Nichely's normal, intended flow.
        6. Analytics + Feedback (Phase 10/11) — if a post from an
           earlier cycle has since been published, refresh its
           analytics and nudge the scoring weights.

    Returns a summary dict describing what happened at each step, so
    the scheduler's log and the Streamlit sidebar can show real status
    instead of just "job ran".
    """
    summary: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": {}}

    articles_stored = run_research_pipeline()
    summary["steps"]["research"] = {"new_articles": articles_stored}

    summary["steps"]["prepare_articles"] = prepare_articles_for_scout()

    run_topic_scout()
    topic, _ = get_selected_topic()
    if topic is None:
        summary["steps"]["topic_scout"] = {"selected_topic": None}
        summary["note"] = "No topic selected this cycle — nothing to generate content for."
        return summary
    summary["steps"]["topic_scout"] = {"selected_topic": topic["headline_candidate"]}

    run_content_strategist(topic["id"])
    with get_session() as session:
        latest_post = session.query(Post).order_by(Post.created_at.desc()).first()
        post_id = latest_post.id if latest_post else None
    summary["steps"]["content_strategist"] = {"post_id": post_id}

    if post_id:
        poster_path = generate_poster_for_latest_pending_post()
        summary["steps"]["poster"] = {"poster_local_path": poster_path}

        if auto_publish and poster_path:
            with get_session() as session:
                db_post = session.query(Post).filter(Post.id == post_id).one()
                db_post.approval_status = "approved"
            publish_result = publish_approved_post(post_id)
            summary["steps"]["publish"] = publish_result

    if run_feedback_for_recent:
        with get_session() as session:
            recent_published = (
                session.query(Post)
                .filter(Post.ig_media_id.isnot(None))
                .order_by(Post.published_at.desc())
                .first()
            )
            recent_id = recent_published.id if recent_published else None

        if recent_id:
            try:
                summary["steps"]["feedback"] = refresh_analytics_and_optimize(recent_id)
            except PipelineError as exc:
                summary["steps"]["feedback"] = {"skipped": str(exc)}

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    return summary


# ---------------------------------------------------------------------
# Phase 12 — scheduler wiring
# ---------------------------------------------------------------------

_scheduler: NichelyScheduler | None = None


def start_scheduler(interval_seconds: float, auto_publish: bool = False) -> NichelyScheduler:
    """Starts running run_full_cycle() on a fixed interval in the
    background. Called from app.py's sidebar toggle. Only one scheduler
    instance is kept module-wide, so re-calling this replaces it."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.stop()

    _scheduler = create_scheduler()
    _scheduler.start_interval(
        lambda: run_full_cycle(auto_publish=auto_publish),
        interval_seconds=interval_seconds,
        run_immediately=True,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running


if __name__ == "__main__":
    print("=" * 60)
    print("NICHELY — FULL PIPELINE CYCLE")
    print(f"Publish mode: {PUBLISH_MODE}")
    print("=" * 60)

    result = run_full_cycle(auto_publish=False)

    print("\nCycle summary:")
    print(json.dumps(result, indent=2, default=str))