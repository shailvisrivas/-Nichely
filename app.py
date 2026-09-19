"""
Phase 8 — Streamlit approval screen + mock publisher.

Shows the ranked topics from Phase 5 (with reasoning), the generated
caption/poster from Phases 6-7, and lets you:
  - Approve & mock-publish
  - Reject WITH feedback, which regenerates a new caption for the same
    topic addressing what was wrong (instead of just marking it dead)
  - Pick a different (shortlisted, not just auto-selected) topic and
    generate content for that one instead

Run with:
    streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st

from database.db import get_session, get_active_weights, get_latest_snapshot_for_post
from database.models import TopicConsidered, Post
from services.poster_service import generate_poster_for_latest_pending_post, generate_carousel_for_post
from services.instagramservice import get_publish_mode, InstagramPublishError
from services.analytics_service import summarize_analytics, AnalyticsError
from agents.content_strategist import list_candidate_topics, create_post_for_topic
import pipeline


st.set_page_config(page_title="Nichely — Approval Screen", layout="centered")
st.title("Nichely — Post Approval")

SUCCESS_SOUND_PATH = Path(__file__).parent / "assets" / "success_sound.wav"


# ---------------------------------------------------------------------
# Sidebar — Phase 12 automation controls + Phase 14 live-readiness check
# ---------------------------------------------------------------------

with st.sidebar:
    st.subheader("Automation")
    current_mode = get_publish_mode()
    st.caption(f"Publish mode: **{current_mode}**")

    if current_mode == "live":
        readiness = pipeline.check_live_readiness()
        if readiness["ready"]:
            st.success("Live publishing is fully configured.")
        else:
            st.warning("Live mode is on, but setup is incomplete:")
            for issue in readiness["issues"]:
                st.caption(f"• {issue}")

    scheduler_running = pipeline.is_scheduler_running()
    if not scheduler_running:
        interval_minutes = st.number_input(
            "Run pipeline every (minutes)", min_value=5, value=60, step=5
        )
        auto_publish = st.checkbox(
            "Auto-publish (skip manual approval)", value=False,
            help="Off = each cycle stops at 'pending' for you to approve below (recommended). "
                 "On = approved automatically and published straight to Instagram/mock.",
        )
        if st.button("▶️ Start scheduled runs"):
            pipeline.start_scheduler(interval_minutes * 60, auto_publish=auto_publish)
            st.rerun()
    else:
        st.success("Scheduler is running.")
        if st.button("⏹️ Stop scheduled runs"):
            pipeline.stop_scheduler()
            st.rerun()

    st.divider()
    if st.button("🔁 Run one pipeline cycle now"):
        with st.spinner("Running research → topics → content → poster..."):
            result = pipeline.run_full_cycle(auto_publish=False)
        st.json(result)


# ---------------------------------------------------------------------
# Load the latest run's ranked topics (Phase 5 output)
# ---------------------------------------------------------------------

with get_session() as session:
    latest_run = (
        session.query(TopicConsidered.run_id)
        .order_by(TopicConsidered.created_at.desc())
        .first()
    )

    if latest_run is None:
        st.warning("No topics found yet — run Phase 5 (topic_scout) first.")
        st.stop()

    run_id = latest_run[0]
    topics = (
        session.query(TopicConsidered)
        .filter(TopicConsidered.run_id == run_id)
        .order_by(TopicConsidered.final_score.desc())
        .all()
    )
    topics_data = [
        {
            "id": t.id,
            "headline_candidate": t.headline_candidate,
            "status": t.status,
            "final_score": t.final_score,
            "score_recency": t.score_recency,
            "score_relevance": t.score_relevance,
            "score_reliability": t.score_reliability,
            "score_novelty": t.score_novelty,
            "score_audience": t.score_audience,
            "reasoning_text": t.reasoning_text,
        }
        for t in topics
    ]


st.subheader("Ranked candidates from this run")
for t in topics_data:
    marker = "🟢 SELECTED" if t["status"] == "selected" else (
        "🟡 shortlisted" if t["status"] == "shortlisted" else "⚪ rejected"
    )
    with st.expander(f"{marker} — [{t['final_score']:.3f}] {t['headline_candidate']}"):
        st.write(
            f"recency={t['score_recency']} · relevance={t['score_relevance']} · "
            f"reliability={t['score_reliability']} · novelty={t['score_novelty']} · "
            f"audience={t['score_audience']}"
        )
        st.caption(t["reasoning_text"])

        if t["status"] == "shortlisted":
            if st.button(
                "✍️ Generate caption for this topic instead",
                key=f"switch_{t['id']}",
            ):
                with st.spinner("Generating content for this topic..."):
                    create_post_for_topic(t["id"])
                st.rerun()


st.divider()


# ---------------------------------------------------------------------
# Load the latest generated post (Phase 6/7 output) for approval
# ---------------------------------------------------------------------

with get_session() as session:
    post = (
        session.query(Post)
        .order_by(Post.created_at.desc())
        .first()
    )

    if post is None:
        st.info("No generated post yet — run Phase 6 (content_strategist) first.")
        st.stop()

    post_data = {
        "id": post.id,
        "topic_id": post.topic_id,
        "headline": post.headline,
        "caption": post.caption,
        "hashtags": json.loads(post.hashtags),
        "cta": post.cta,
        "source_attribution": json.loads(post.source_attribution or "[]"),
        "poster_local_path": post.poster_local_path,
        "poster_local_paths": post.poster_local_paths,
        "approval_status": post.approval_status,
    }


st.subheader("Generated post")


if not post_data["poster_local_path"]:
    if st.button("Generate poster image"):
        with st.spinner("Generating poster image..."):
            path = generate_poster_for_latest_pending_post()

        if path:
            st.rerun()
        else:
            st.warning(
                "Poster service found nothing pending — check services/poster_service.py."
            )

elif post_data.get("poster_local_paths"):
    slide_paths = json.loads(post_data["poster_local_paths"])
    cols = st.columns(len(slide_paths))

    for col, slide_path in zip(cols, slide_paths):
        col.image(slide_path, use_container_width=True)

else:
    st.image(post_data["poster_local_path"], width=400)

    if st.button("🎠 Generate carousel (multi-slide) from this post"):
        with st.spinner("Generating carousel slides..."):
            generate_carousel_for_post(post_data["id"])
        st.rerun()


st.markdown(f"**Headline:** {post_data['headline']}")
st.markdown(f"**Caption:** {post_data['caption']}")
st.markdown(f"**CTA:** {post_data['cta']}")
st.markdown(
    "**Hashtags:** "
    + " ".join(f"#{h.lstrip('#')}" for h in post_data["hashtags"])
)
st.caption(f"Sources: {', '.join(post_data['source_attribution'])}")


st.divider()


if post_data["approval_status"] not in ("pending",):
    st.success(f"This post is already: {post_data['approval_status']}")

elif "rejecting" not in st.session_state:
    st.session_state.rejecting = False


if post_data["approval_status"] == "pending" and not st.session_state.get(
    "rejecting", False
):
    col1, col2 = st.columns(2)

    approve_label = (
        "✅ Approve & Publish"
        if get_publish_mode() == "live"
        else "✅ Approve & Publish (mock)"
    )

    if col1.button(approve_label, type="primary"):
        with get_session() as session:
            db_post = (
                session.query(Post)
                .filter(Post.id == post_data["id"])
                .one()
            )
            db_post.approval_status = "approved"

        with st.spinner("Publishing..."):
            try:
                result = pipeline.publish_approved_post(post_data["id"])

                if result["mode"] == "live":
                    st.success(
                        f"Published to Instagram! Media ID: {result['media_id']}"
                    )
                else:
                    st.success(
                        "Published (mock) — logged to the database instead of real Instagram."
                    )

                if SUCCESS_SOUND_PATH.exists():
                    st.audio(
                        str(SUCCESS_SOUND_PATH),
                        autoplay=True,
                    )
                else:
                    st.warning(
                        f"Success sound not found: {SUCCESS_SOUND_PATH}"
                    )

            except InstagramPublishError as exc:
                with get_session() as session:
                    db_post = (
                        session.query(Post)
                        .filter(Post.id == post_data["id"])
                        .one()
                    )
                    db_post.approval_status = "pending"

                st.error(
                    f"Publishing failed, post left as pending: {exc}"
                )

        st.rerun()

    if col2.button("❌ Reject"):
        st.session_state.rejecting = True
        st.rerun()


elif (
    post_data["approval_status"] == "pending"
    and st.session_state.get("rejecting", False)
):
    st.markdown(
        "**What should change?** "
        "(e.g. \"too formal\", \"wrong tone\", \"hashtags don't fit\")"
    )

    feedback = st.text_area(
        "Feedback",
        label_visibility="collapsed",
        key="reject_feedback",
    )

    col1, col2 = st.columns(2)

    if col1.button(
        "🔁 Regenerate with this feedback",
        type="primary",
        disabled=not feedback.strip(),
    ):
        with get_session() as session:
            db_post = (
                session.query(Post)
                .filter(Post.id == post_data["id"])
                .one()
            )
            db_post.approval_status = "rejected"

        with st.spinner("Regenerating with your feedback..."):
            create_post_for_topic(
                post_data["topic_id"],
                feedback=feedback,
            )

        st.session_state.rejecting = False
        st.rerun()

    if col2.button("Cancel"):
        st.session_state.rejecting = False
        st.rerun()


# ---------------------------------------------------------------------
# Phase 10/11 — analytics + feedback optimization, once published
# ---------------------------------------------------------------------

if post_data["approval_status"] == "approved":
    st.divider()
    st.subheader("Performance & feedback")

    snapshot = get_latest_snapshot_for_post(post_data["id"])

    if snapshot:
        st.caption(f"Last fetched: {snapshot['fetched_at']}")
        st.write(summarize_analytics(snapshot))
    else:
        st.caption("No analytics fetched yet for this post.")

    col1, col2 = st.columns(2)

    if col1.button("📊 Fetch analytics"):
        with st.spinner("Fetching Instagram analytics..."):
            try:
                result = pipeline.refresh_analytics_and_optimize(
                    post_data["id"]
                )
                st.success(
                    "Analytics refreshed and scoring weights updated."
                )
                st.write(summarize_analytics(result["analytics"]))
                st.caption(result["optimization"]["reasoning"])

            except (AnalyticsError, pipeline.PipelineError) as exc:
                st.error(f"Could not fetch analytics: {exc}")

        st.rerun()

    if col2.button("🧠 Show current scoring weights"):
        st.json(get_active_weights())

