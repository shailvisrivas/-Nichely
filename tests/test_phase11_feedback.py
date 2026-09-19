"""
Phase 11 test — Feedback / Optimization Agent.

This test uses simulated Phase 10 analytics.
No Instagram API is required.

Run with:

    python -m tests.test_phase11_feedback
"""

from services.feedback_service import (
    calculate_performance_score,
    run_feedback_optimization,
)


def run():

    print(
        "Starting Phase 11 Feedback / Optimization test..."
    )

    # -----------------------------------------------------
    # Simulated Phase 10 result
    # -----------------------------------------------------

    analytics = {
        "success": True,
        "mode": "mock",
        "media_id": "mock_media_123",
        "likes": 128,
        "comments": 17,
        "reach": 2450,
        "saves": 63,
        "shares": 31,
        "engagement_rate": 0.0976,
    }

    print(
        "\nUsing Phase 10 analytics:"
    )

    print(
        f"  Likes: {analytics['likes']}"
    )

    print(
        f"  Comments: {analytics['comments']}"
    )

    print(
        f"  Reach: {analytics['reach']}"
    )

    print(
        f"  Saves: {analytics['saves']}"
    )

    print(
        f"  Shares: {analytics['shares']}"
    )

    print(
        f"  Engagement rate: "
        f"{analytics['engagement_rate']:.2%}"
    )

    # -----------------------------------------------------
    # Calculate performance
    # -----------------------------------------------------

    performance = calculate_performance_score(
        analytics
    )

    print(
        "\nCalculated performance score:"
    )

    print(
        f"  {performance:.3f}"
    )

    # -----------------------------------------------------
    # Run optimization
    # -----------------------------------------------------

    print(
        "\nRunning Feedback Agent..."
    )

    result = run_feedback_optimization(
        analytics
    )

    print(
        "\nFeedback optimization completed."
    )

    print(
        f"Performance score: "
        f"{result['performance_score']:.3f}"
    )

    # -----------------------------------------------------
    # Display old weights
    # -----------------------------------------------------

    print(
        "\nOLD SCORING WEIGHTS:"
    )

    for key, value in result["old_weights"].items():
        print(
            f"  {key}: {value:.4f}"
        )

    # -----------------------------------------------------
    # Display new weights
    # -----------------------------------------------------

    print(
        "\nNEW SCORING WEIGHTS:"
    )

    for key, value in result["new_weights"].items():
        print(
            f"  {key}: {value:.4f}"
        )

    # -----------------------------------------------------
    # Display explanation
    # -----------------------------------------------------

    print(
        "\nWHY THE WEIGHTS CHANGED:"
    )

    print(
        f"  {result['reasoning']}"
    )

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    total = sum(
        result["new_weights"].values()
    )

    print(
        "\nWeight validation:"
    )

    print(
        f"  Total weight: {total:.4f}"
    )

    if abs(total - 1.0) > 0.001:
        raise AssertionError(
            "Scoring weights do not add up to 1.0."
        )

    for key, value in result["new_weights"].items():

        if not 0.05 <= value <= 0.50:
            raise AssertionError(
                f"{key} is outside the allowed range."
            )

    print(
        "  All weights are valid."
    )

    print(
        "\nPhase 11 Feedback / Optimization test "
        "completed successfully."
    )


if __name__ == "__main__":
    run()