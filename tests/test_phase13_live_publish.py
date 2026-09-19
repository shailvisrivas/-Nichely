"""
Phase 13 test — real Instagram publishing (live mode).

This does NOT hit the real Meta Graph API or require real credentials.
It patches services.instagramservice's HTTP calls and checks that the
two-step container -> publish flow is wired correctly, and that
missing-credential / API-error cases are handled without crashing.

Run with:
    python -m tests.test_phase13_live_publish
"""

from unittest.mock import patch

from services import instagramservice as ig


def run():
    print("Starting Phase 13 live-publish test (mocked, no real API calls)...")

    # -----------------------------------------------------
    # Test 1: missing credentials are caught before any request
    # -----------------------------------------------------
    print("\nTesting missing-credential guard...")
    with patch.object(ig, "PUBLISH_MODE", "live"), \
         patch.object(ig, "IG_APP_ID", None), \
         patch.object(ig, "IG_APP_SECRET", None), \
         patch.object(ig, "IG_ACCESS_TOKEN", None), \
         patch.object(ig, "IG_USER_ID", None):
        try:
            ig.publish_post("caption", "https://example.com/poster.jpg")
            raise AssertionError("Expected InstagramPublishError for missing credentials.")
        except ig.InstagramPublishError as exc:
            assert "IG_APP_ID" in str(exc)
            print(f"  Correctly rejected: {exc}")

    # -----------------------------------------------------
    # Test 2: successful two-step publish (container -> ready -> publish)
    # -----------------------------------------------------
    print("\nTesting successful live publish flow...")

    def fake_meta_request(method, endpoint, params):
        if endpoint.endswith("/media"):
            return {"id": "container_123"}
        if endpoint == "container_123":
            return {"status_code": "FINISHED"}
        if endpoint.endswith("/media_publish"):
            return {"id": "media_456"}
        raise AssertionError(f"Unexpected endpoint called: {endpoint}")

    with patch.object(ig, "PUBLISH_MODE", "live"), \
         patch.object(ig, "IG_APP_ID", "app_id"), \
         patch.object(ig, "IG_APP_SECRET", "app_secret"), \
         patch.object(ig, "IG_ACCESS_TOKEN", "token"), \
         patch.object(ig, "IG_USER_ID", "ig_user_id"), \
         patch.object(ig, "_meta_request", side_effect=fake_meta_request):
        result = ig.publish_post("Test caption #nichely", "https://public-host.example/poster.jpg")

        assert result["success"] is True
        assert result["mode"] == "live"
        assert result["media_id"] == "media_456"
        print(f"  Published. media_id={result['media_id']}")

    # -----------------------------------------------------
    # Test 3: container errors out during processing
    # -----------------------------------------------------
    print("\nTesting container ERROR status handling...")

    def failing_meta_request(method, endpoint, params):
        if endpoint.endswith("/media"):
            return {"id": "container_bad"}
        if endpoint == "container_bad":
            return {"status_code": "ERROR"}
        raise AssertionError("Should not reach media_publish after an ERROR status.")

    with patch.object(ig, "PUBLISH_MODE", "live"), \
         patch.object(ig, "IG_APP_ID", "app_id"), \
         patch.object(ig, "IG_APP_SECRET", "app_secret"), \
         patch.object(ig, "IG_ACCESS_TOKEN", "token"), \
         patch.object(ig, "IG_USER_ID", "ig_user_id"), \
         patch.object(ig, "_meta_request", side_effect=failing_meta_request):
        try:
            ig.publish_post("caption", "https://public-host.example/poster.jpg")
            raise AssertionError("Expected InstagramPublishError for container ERROR status.")
        except ig.InstagramPublishError as exc:
            print(f"  Correctly surfaced container error: {exc}")

    print("\nPhase 13 live-publish test completed successfully.")


if __name__ == "__main__":
    run()
