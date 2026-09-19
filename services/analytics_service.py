"""
Analytics Service — Phase 10.

Collects Instagram post performance metrics.

Current behavior:
    PUBLISH_MODE=mock
        -> returns simulated analytics for testing.

    PUBLISH_MODE=live
        -> calls the Meta Graph API to retrieve Instagram
           media metrics.

The service is designed so that Phase 10 can be tested
without having the real Instagram API configured yet.
"""

import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------

load_dotenv()

PUBLISH_MODE = os.getenv("PUBLISH_MODE", "mock").lower()

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")

META_GRAPH_API_VERSION = os.getenv(
    "META_GRAPH_API_VERSION",
    "v23.0",
)

META_GRAPH_BASE_URL = f"https://graph.instagram.com/{META_GRAPH_API_VERSION}"


# ---------------------------------------------------------
# Custom error
# ---------------------------------------------------------

class AnalyticsError(RuntimeError):
    """Raised when Instagram analytics cannot be retrieved."""


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

def validate_media_id(media_id: str) -> None:
    """Validate the Instagram media ID."""

    if not media_id or not str(media_id).strip():
        raise AnalyticsError(
            "Instagram media ID cannot be empty."
        )


# ---------------------------------------------------------
# Mock analytics
# ---------------------------------------------------------

def _get_mock_analytics(media_id: str) -> dict:
    """
    Return simulated Instagram analytics.

    This allows Phase 10 to be tested before the
    Meta/Instagram API is connected.
    """

    return {
        "success": True,
        "mode": "mock",
        "media_id": media_id,
        "likes": 128,
        "comments": 17,
        "reach": 2450,
        "saves": 63,
        "shares": 31,
        "engagement_rate": round(
            (128 + 17 + 63 + 31) / 2450,
            4,
        ),
        "fetched_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ---------------------------------------------------------
# Meta API helper
# ---------------------------------------------------------

def _meta_get(
    endpoint: str,
    params: dict[str, Any],
) -> dict:
    """Send a GET request to the Meta Graph API."""

    try:
        response = requests.get(
            f"{META_GRAPH_BASE_URL}/{endpoint}",
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise AnalyticsError(
            f"Could not connect to Meta Graph API: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AnalyticsError(
            f"Meta Graph API returned a non-JSON response "
            f"(HTTP {response.status_code})."
        ) from exc

    if response.status_code >= 400:
        error = payload.get("error", {})

        message = error.get(
            "message",
            "Unknown Meta Graph API error.",
        )

        raise AnalyticsError(
            f"Meta Graph API error "
            f"(HTTP {response.status_code}): {message}"
        )

    return payload


# ---------------------------------------------------------
# Live Instagram analytics
# ---------------------------------------------------------

def _get_live_analytics(media_id: str) -> dict:
    """
    Retrieve Instagram analytics from the Meta Graph API.

    The media object provides:
        - like_count
        - comments_count

    The insights endpoint provides:
        - reach
        - saved
        - shares
    """

    if not IG_ACCESS_TOKEN:
        raise AnalyticsError(
            "IG_ACCESS_TOKEN is not set. "
            "Add it to the .env file before using "
            "live analytics."
        )

    # -----------------------------------------------------
    # Get basic media metrics
    # -----------------------------------------------------

    media_data = _meta_get(
        media_id,
        {
            "fields": "id,like_count,comments_count",
            "access_token": IG_ACCESS_TOKEN,
        },
    )

    likes = int(
        media_data.get("like_count", 0) or 0
    )

    comments = int(
        media_data.get("comments_count", 0) or 0
    )

    # -----------------------------------------------------
    # Get Instagram media insights
    # -----------------------------------------------------

    insights_data = _meta_get(
        f"{media_id}/insights",
        {
            "metric": "reach,saved,shares",
            "access_token": IG_ACCESS_TOKEN,
        },
    )

    insights = {}

    for item in insights_data.get("data", []):
        name = item.get("name")

        values = item.get("values", [])

        if values:
            insights[name] = values[-1].get(
                "value",
                0,
            )

    reach = int(
        insights.get("reach", 0) or 0
    )

    saves = int(
        insights.get("saved", 0) or 0
    )

    shares = int(
        insights.get("shares", 0) or 0
    )

    # -----------------------------------------------------
    # Calculate engagement rate
    # -----------------------------------------------------

    engagement_rate = 0.0

    if reach > 0:
        engagement_rate = (
            likes
            + comments
            + saves
            + shares
        ) / reach

    return {
        "success": True,
        "mode": "live",
        "media_id": media_id,
        "likes": likes,
        "comments": comments,
        "reach": reach,
        "saves": saves,
        "shares": shares,
        "engagement_rate": round(
            engagement_rate,
            4,
        ),
        "fetched_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ---------------------------------------------------------
# Public function
# ---------------------------------------------------------

def get_post_analytics(
    media_id: str,
) -> dict:
    """
    Get analytics for an Instagram post.

    In mock mode:
        Returns simulated metrics.

    In live mode:
        Calls the Meta Graph API.

    Parameters:
        media_id:
            Instagram media/post ID.

    Returns:
        Dictionary containing:
            likes
            comments
            reach
            saves
            shares
            engagement_rate
            mode
            media_id
    """

    validate_media_id(media_id)

    if PUBLISH_MODE == "mock":
        return _get_mock_analytics(
            media_id
        )

    if PUBLISH_MODE == "live":
        return _get_live_analytics(
            media_id
        )

    raise AnalyticsError(
        f"Unsupported PUBLISH_MODE: {PUBLISH_MODE}. "
        "Use 'mock' or 'live'."
    )


# ---------------------------------------------------------
# Simple performance summary
# ---------------------------------------------------------

def summarize_analytics(
    analytics: dict,
) -> str:
    """
    Convert analytics into a simple explanation
    suitable for the Nichely demo.
    """

    return (
        f"This Instagram post received "
        f"{analytics['likes']} likes, "
        f"{analytics['comments']} comments, "
        f"{analytics['reach']} reach, "
        f"{analytics['saves']} saves, and "
        f"{analytics['shares']} shares. "
        f"The engagement rate was "
        f"{analytics['engagement_rate']:.2%}."
    )


# ---------------------------------------------------------
# Direct execution
# ---------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("PHASE 10 — INSTAGRAM ANALYTICS")
    print("=" * 60)

    print(f"\nAnalytics mode: {PUBLISH_MODE}")

    # Dummy media ID for mock testing.
    test_media_id = "mock_media_123"

    try:
        analytics = get_post_analytics(
            test_media_id
        )

        print("\nAnalytics retrieved successfully.")

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

        print("\nSummary:")
        print(
            summarize_analytics(
                analytics
            )
        )

    except AnalyticsError as exc:
        print(
            f"\nAnalytics error: {exc}"
        )