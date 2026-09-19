"""
Phase 9 test — Instagram publishing.

For now this test runs in MOCK mode, so it does not publish
anything to Instagram.

Run with:

    python -m tests.test_phase9_instagram
"""

from services.instagramservice import (
    InstagramPublishError,
    get_publish_mode,
    publish_post,
)


def run():
    print("Starting Phase 9 Instagram publisher test...")
    print(f"Publishing mode: {get_publish_mode()}")

    print()
    print("Testing mock Instagram publishing...")

    try:
        result = publish_post(
            caption="Nichely Phase 9 test post.",
            image_url="https://example.com/test-image.jpg",
        )

        print("Publish call completed.")
        print(f"Success: {result['success']}")
        print(f"Mode: {result['mode']}")
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")

    except InstagramPublishError as e:
        print(f"Instagram publishing error: {e}")
        return

    print()
    print("Phase 9 publisher module loaded successfully.")
    print("No real Instagram post was created or published.")


if __name__ == "__main__":
    run()