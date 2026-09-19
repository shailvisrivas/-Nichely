"""
Feedback / Optimization Agent — Phase 11.

Uses Instagram post performance from Phase 10 to adjust the
Topic Scout scoring weights used in Phase 5.

The optimization is deliberately simple and explainable:

- Strong performance increases the importance of the criteria
  associated with the post.
- Weak performance decreases their importance.
- Weights are normalized so that they always add up to 1.0.
- Changes are kept within safe limits to prevent large jumps.

Current Phase 11 implementation supports mock analytics so it
can be tested before the real Instagram API is connected.
"""

from __future__ import annotations

from typing import Any

from config import DEFAULT_SCORING_WEIGHTS


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.50

# Maximum adjustment applied to an individual weight
MAX_ADJUSTMENT = 0.05


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """Keep a number inside a specified range."""

    return max(
        minimum,
        min(maximum, value),
    )


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """Convert a value to float safely."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------
# Performance calculation
# ---------------------------------------------------------

def calculate_performance_score(
    analytics: dict,
) -> float:
    """
    Calculate a normalized performance score from Instagram
    analytics.

    The score combines:

        engagement rate
        reach
        saves
        shares

    The result is between 0.0 and 1.0.
    """

    engagement_rate = _safe_float(
        analytics.get("engagement_rate")
    )

    reach = _safe_float(
        analytics.get("reach")
    )

    saves = _safe_float(
        analytics.get("saves")
    )

    shares = _safe_float(
        analytics.get("shares")
    )

    # Engagement rate is already represented as a decimal.
    # For example:
    # 0.10 = 10%

    engagement_component = _clamp(
        engagement_rate / 0.10,
        0.0,
        1.0,
    )

    # These are deliberately capped so unusually large posts
    # do not completely dominate the optimization.

    reach_component = _clamp(
        reach / 10000.0,
        0.0,
        1.0,
    )

    saves_component = _clamp(
        saves / 500.0,
        0.0,
        1.0,
    )

    shares_component = _clamp(
        shares / 250.0,
        0.0,
        1.0,
    )

    score = (
        engagement_component * 0.40
        + reach_component * 0.20
        + saves_component * 0.20
        + shares_component * 0.20
    )

    return round(
        _clamp(score, 0.0, 1.0),
        4,
    )


# ---------------------------------------------------------
# Optimization
# ---------------------------------------------------------

def optimize_weights(
    current_weights: dict | None,
    analytics: dict,
) -> dict:
    """
    Adjust Topic Scout scoring weights using post performance.

    High performance:
        increases the weights of novelty and audience interest.

    Low performance:
        slightly shifts weight toward recency and relevance.

    Reliability remains comparatively stable because source
    reliability is a quality control factor rather than a
    performance-driven content preference.
    """

    if current_weights is None:
        current_weights = dict(
            DEFAULT_SCORING_WEIGHTS
        )

    performance = calculate_performance_score(
        analytics
    )

    new_weights = dict(current_weights)

    # -----------------------------------------------------
    # Determine whether performance was strong or weak
    # -----------------------------------------------------

    if performance >= 0.60:
        # Strong post performance.
        #
        # Increase novelty and audience interest because
        # these are useful signals for identifying topics
        # that attract engagement.

        new_weights["w_novelty"] += MAX_ADJUSTMENT
        new_weights["w_audience"] += MAX_ADJUSTMENT

        new_weights["w_recency"] -= MAX_ADJUSTMENT / 2
        new_weights["w_relevance"] -= MAX_ADJUSTMENT / 2

    elif performance < 0.30:
        # Weak post performance.
        #
        # Put slightly more emphasis on recency and relevance
        # for the next round.

        new_weights["w_recency"] += MAX_ADJUSTMENT
        new_weights["w_relevance"] += MAX_ADJUSTMENT

        new_weights["w_novelty"] -= MAX_ADJUSTMENT / 2
        new_weights["w_audience"] -= MAX_ADJUSTMENT / 2

    # -----------------------------------------------------
    # Clamp individual weights
    # -----------------------------------------------------

    for key in new_weights:
        new_weights[key] = _clamp(
            _safe_float(new_weights[key]),
            MIN_WEIGHT,
            MAX_WEIGHT,
        )

    # -----------------------------------------------------
    # Normalize weights
    # -----------------------------------------------------

    total = sum(
        new_weights.values()
    )

    if total <= 0:
        raise RuntimeError(
            "Invalid scoring weights: total weight is zero."
        )

    for key in new_weights:
        new_weights[key] = round(
            new_weights[key] / total,
            4,
        )

    # Correct tiny floating-point rounding differences.
    difference = round(
        1.0 - sum(new_weights.values()),
        4,
    )

    new_weights["w_relevance"] = round(
        new_weights["w_relevance"] + difference,
        4,
    )

    return new_weights


# ---------------------------------------------------------
# Explain the optimization
# ---------------------------------------------------------

def explain_optimization(
    old_weights: dict,
    new_weights: dict,
    analytics: dict,
) -> str:
    """
    Create a plain-English explanation of the feedback decision.
    """

    performance = calculate_performance_score(
        analytics
    )

    if performance >= 0.60:
        performance_description = "strong"
        strategy = (
            "Nichely increased the importance of novelty and "
            "audience interest because the post performed strongly."
        )

    elif performance < 0.30:
        performance_description = "weak"
        strategy = (
            "Nichely increased the importance of recency and "
            "relevance because the post performance was weak."
        )

    else:
        performance_description = "moderate"
        strategy = (
            "Nichely kept the scoring strategy stable because "
            "the post performance was moderate."
        )

    changes = []

    for key in old_weights:
        old_value = _safe_float(
            old_weights.get(key)
        )

        new_value = _safe_float(
            new_weights.get(key)
        )

        difference = new_value - old_value

        if abs(difference) >= 0.001:
            changes.append(
                f"{key}: {old_value:.3f} → {new_value:.3f}"
            )

    change_text = (
        "; ".join(changes)
        if changes
        else "No significant weight changes."
    )

    return (
        f"The post achieved a {performance_description} "
        f"performance score of {performance:.3f}. "
        f"{strategy} "
        f"Weight changes: {change_text}"
    )


# ---------------------------------------------------------
# Main Phase 11 function
# ---------------------------------------------------------

def run_feedback_optimization(
    analytics: dict,
    current_weights: dict | None = None,
) -> dict:
    """
    Run the complete Phase 11 optimization process.

    Parameters:
        analytics:
            Performance metrics returned by Phase 10.

        current_weights:
            Current Topic Scout weights. If omitted,
            DEFAULT_SCORING_WEIGHTS are used.

    Returns:
        {
            "performance_score": ...,
            "old_weights": ...,
            "new_weights": ...,
            "reasoning": ...
        }
    """

    if not analytics:
        raise RuntimeError(
            "No analytics data supplied to Feedback Agent."
        )

    if current_weights is None:
        current_weights = dict(
            DEFAULT_SCORING_WEIGHTS
        )
    else:
        current_weights = dict(
            current_weights
        )

    required_weights = {
        "w_recency",
        "w_relevance",
        "w_reliability",
        "w_novelty",
        "w_audience",
    }

    missing = required_weights - set(
        current_weights.keys()
    )

    if missing:
        raise RuntimeError(
            "Missing scoring weights: "
            + ", ".join(sorted(missing))
        )

    new_weights = optimize_weights(
        current_weights,
        analytics,
    )

    performance_score = calculate_performance_score(
        analytics
    )

    reasoning = explain_optimization(
        current_weights,
        new_weights,
        analytics,
    )

    return {
        "performance_score": performance_score,
        "old_weights": current_weights,
        "new_weights": new_weights,
        "reasoning": reasoning,
    }


# ---------------------------------------------------------
# Direct execution
# ---------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("PHASE 11 — FEEDBACK / OPTIMIZATION AGENT")
    print("=" * 60)

    # Example analytics.
    # These are the same kind of values returned by Phase 10.

    example_analytics = {
        "likes": 128,
        "comments": 17,
        "reach": 2450,
        "saves": 63,
        "shares": 31,
        "engagement_rate": 0.0976,
    }

    print("\nInput analytics:")

    for key, value in example_analytics.items():
        print(
            f"  {key}: {value}"
        )

    result = run_feedback_optimization(
        example_analytics
    )

    print("\nPerformance score:")
    print(
        f"  {result['performance_score']:.3f}"
    )

    print("\nOld weights:")

    for key, value in result["old_weights"].items():
        print(
            f"  {key}: {value:.4f}"
        )

    print("\nNew weights:")

    for key, value in result["new_weights"].items():
        print(
            f"  {key}: {value:.4f}"
        )

    print("\nWhy the weights changed:")
    print(
        f"  {result['reasoning']}"
    )

    print("\nPhase 11 completed successfully.")