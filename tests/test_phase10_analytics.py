"""
Phase 10 test — Instagram Analytics.

Currently runs in mock mode, so no real Instagram API
credentials are required.

Run with:

    python -m tests.test_phase10_analytics
"""

from services.analytics_service import (
    AnalyticsError,
    get_post_analytics,
    summarize_analytics,
)


def run():
    print(
        "Starting Phase 10 Instagram Analytics test..."
    )

    print(
        "Analytics mode: mock"
    )

    print(
        "\nTesting mock Instagram analytics..."
    )

    media_id = "mock_media_123"

    try:
        analytics = get_post_analytics(
            media_id
        )

    except AnalyticsError as exc:
        print(
            f"\nAnalytics test failed: {exc}"
        )
        return

    print(
        "Analytics call completed."
    )

    print(
        f"Success: "
        f"{analytics['success']}"
    )

    print(
        f"Mode: "
        f"{analytics['mode']}"
    )

    print(
        f"Media ID: "
        f"{analytics['media_id']}"
    )

    print(
        f"Likes: "
        f"{analytics['likes']}"
    )

    print(
        f"Comments: "
        f"{analytics['comments']}"
    )

    print(
        f"Reach: "
        f"{analytics['reach']}"
    )

    print(
        f"Saves: "
        f"{analytics['saves']}"
    )

    print(
        f"Shares: "
        f"{analytics['shares']}"
    )

    print(
        f"Engagement rate: "
        f"{analytics['engagement_rate']:.2%}"
    )

    print(
        "\nPerformance summary:"
    )

    print(
        f"  {summarize_analytics(analytics)}"
    )

    print(
        "\nPhase 10 Analytics test completed successfully."
    )


if __name__ == "__main__":
    run()