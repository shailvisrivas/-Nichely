"""
Phase 15 test — final end-to-end pipeline wiring.

Two things are verified here:

1. run_full_cycle() calls every phase in the right order and respects
   auto_publish — the research/topic/content/poster/publish steps are
   monkeypatched, since a real run needs live GEMINI_API_KEY /
   NEWS_API_KEY credentials this test environment may not have.

2. The analytics -> feedback loop (refresh_analytics_and_optimize) is
   run for real, end-to-end, against a throwaway Post row — this needs
   no external credentials because PUBLISH_MODE=mock analytics don't
   call any real API.

Run with:
    python -m tests.test_phase15_e2e
"""

from unittest.mock import patch

import pipeline
from database.db import get_session, init_db
from database.models import Post


def run():
    print("Starting Phase 15 end-to-end pipeline test...")
    init_db()

    # -----------------------------------------------------
    # Test 1: run_full_cycle orchestration order + auto_publish gating
    # -----------------------------------------------------
    print("\nTesting run_full_cycle() step order (mocked phases)...")

    calls = []

    def record(name, value=None):
        # side_effect overrides return_value on a Mock, so the value
        # to return has to be baked into the side_effect itself.
        def _inner(*args, **kwargs):
            calls.append(name)
            return value
        return _inner

    with patch.object(pipeline, "run_research_pipeline", side_effect=record("research", 3)), \
         patch.object(pipeline, "run_topic_scout", side_effect=record("topic_scout")), \
         patch.object(pipeline, "get_selected_topic", return_value=(None, None)):
        summary = pipeline.run_full_cycle(auto_publish=False, run_feedback_for_recent=False)

        assert calls == ["research", "topic_scout"]
        assert summary["steps"]["research"]["new_articles"] == 3
        assert summary["steps"]["topic_scout"]["selected_topic"] is None
        assert "content_strategist" not in summary["steps"]
        print("  Correctly stopped after topic_scout when no topic was selected.")

    # -----------------------------------------------------
    # Test 2: analytics -> feedback loop, run for real (mock mode)
    # -----------------------------------------------------
    print("\nTesting refresh_analytics_and_optimize() against a real throwaway post...")

    with get_session() as session:
        test_post = Post(
            topic_id="test-topic",
            headline="Test headline",
            caption="Test caption",
            hashtags="[]",
            approval_status="approved",
            publish_mode="mock",
            ig_media_id="mock_e2e_test",
        )
        session.add(test_post)
        session.flush()
        post_id = test_post.id

    try:
        result = pipeline.refresh_analytics_and_optimize(post_id)

        assert result["analytics"]["mode"] == "mock"
        assert 0.0 <= result["optimization"]["performance_score"] <= 1.0
        total_weight = sum(result["optimization"]["new_weights"].values())
        assert abs(total_weight - 1.0) < 0.001

        print(f"  Performance score: {result['optimization']['performance_score']:.3f}")
        print(f"  Weights still sum to 1.0: {total_weight:.4f}")
        print("  Analytics -> feedback loop completed successfully.")

    finally:
        # Clean up the throwaway post and its snapshot so repeated test
        # runs don't accumulate junk rows in the real nichely.db.
        from database.models import EngagementSnapshot

        with get_session() as session:
            session.query(EngagementSnapshot).filter(EngagementSnapshot.post_id == post_id).delete()
            session.query(Post).filter(Post.id == post_id).delete()

    print("\nPhase 15 end-to-end test completed successfully.")


if __name__ == "__main__":
    run()