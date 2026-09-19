"""
Instagram publishing service — Phase 9 (mock) + Phase 13 (real).

Handles the final publishing step for Nichely.

    PUBLISH_MODE=mock
        No real Instagram API request is made. The service validates
        the post information and simulates publishing. This is the
        safe default and what Phases 9-12 were built and tested against.

    PUBLISH_MODE=live
        Publishes for real via the Meta Graph API, using the standard
        two-step Instagram Content Publishing flow:
            1. Create a media container (IG_USER_ID/media) from a
               *public* image URL + caption.
            2. Publish that container (IG_USER_ID/media_publish).
        This requires IG_APP_ID, IG_APP_SECRET, IG_ACCESS_TOKEN and
        IG_USER_ID to be set in .env, and image_url must be a public
        HTTPS URL (see services/cloud_upload_service.py) — Instagram
        cannot fetch a local file path.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

PUBLISH_MODE = os.getenv("PUBLISH_MODE", "mock").lower()

IG_APP_ID = os.getenv("IG_APP_ID")
IG_APP_SECRET = os.getenv("IG_APP_SECRET")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0")
META_GRAPH_BASE_URL = f"https://graph.instagram.com/{META_GRAPH_API_VERSION}"
# How long to wait for Instagram to finish downloading/processing the
# container image before giving up on publishing it.
CONTAINER_STATUS_TIMEOUT_SECONDS = 60
CONTAINER_STATUS_POLL_SECONDS = 3


class InstagramPublishError(RuntimeError):
    """Raised when an Instagram publishing operation fails."""


def validate_post(caption: str, image_url: str) -> None:
    """Validate the information required for an Instagram post."""

    if not caption or not caption.strip():
        raise InstagramPublishError("Instagram post caption cannot be empty.")

    if not image_url or not image_url.strip():
        raise InstagramPublishError("Instagram post image URL cannot be empty.")


def _require_live_credentials() -> None:
    missing = []
    if not IG_APP_ID:
        missing.append("IG_APP_ID")
    if not IG_APP_SECRET:
        missing.append("IG_APP_SECRET")
    if not IG_ACCESS_TOKEN:
        missing.append("IG_ACCESS_TOKEN")
    if not IG_USER_ID:
        missing.append("IG_USER_ID")

    if missing:
        raise InstagramPublishError(
            "Instagram live publishing requires: " + ", ".join(missing)
        )


def _meta_request(method: str, endpoint: str, params: dict[str, Any]) -> dict:
    """Send a request to the Meta Graph API and surface errors clearly."""

    url = f"{META_GRAPH_BASE_URL}/{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=30)
        else:
            response = requests.post(url, data=params, timeout=30)
    except requests.RequestException as exc:
        raise InstagramPublishError(f"Could not connect to Meta Graph API: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise InstagramPublishError(
            f"Meta Graph API returned a non-JSON response (HTTP {response.status_code})."
        ) from exc

    if response.status_code >= 400:
        error = payload.get("error", {})
        message = error.get("message", "Unknown Meta Graph API error.")
        code = error.get("code")
        subcode = error.get("error_subcode")
        raise InstagramPublishError(
            f"Meta Graph API error (HTTP {response.status_code}, code={code}, "
            f"subcode={subcode}): {message}"
        )

    return payload


def _create_media_container(caption: str, image_url: str) -> str:
    """Step 1 of live publishing: ask Instagram to fetch the image and
    prepare it as an unpublished media container. Returns the
    container id."""

    payload = _meta_request(
        "POST",
        f"{IG_USER_ID}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        },
    )

    container_id = payload.get("id")
    if not container_id:
        raise InstagramPublishError(
            f"Media container creation did not return an id: {payload}"
        )

    return container_id


def _wait_for_container_ready(container_id: str) -> None:
    """Polls the container's status_code until it's FINISHED (ready to
    publish), or raises if it errors out or times out. Instagram
    downloads/processes the image asynchronously, so this step can't be
    skipped for larger images."""

    deadline = time.time() + CONTAINER_STATUS_TIMEOUT_SECONDS

    while True:
        payload = _meta_request(
            "GET",
            container_id,
            {"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
        )

        status = payload.get("status_code")

        if status == "FINISHED":
            return

        if status == "ERROR":
            raise InstagramPublishError(
                f"Instagram failed to process the media container: {payload}"
            )

        if time.time() >= deadline:
            raise InstagramPublishError(
                f"Timed out waiting for media container {container_id} to finish "
                f"processing (last status: {status})."
            )

        time.sleep(CONTAINER_STATUS_POLL_SECONDS)


def _publish_media_container(container_id: str) -> str:
    """Step 2 of live publishing: publish the ready container. Returns
    the published media id."""

    payload = _meta_request(
        "POST",
        f"{IG_USER_ID}/media_publish",
        {
            "creation_id": container_id,
            "access_token": IG_ACCESS_TOKEN,
        },
    )

    media_id = payload.get("id")
    if not media_id:
        raise InstagramPublishError(f"Publish call did not return a media id: {payload}")

    return media_id


def _create_carousel_item_container(image_url: str) -> str:
    """Phase 16 (carousel feature) -- creates one carousel-item
    container from an image. This is NOT published on its own; it only
    becomes a child of a parent CAROUSEL container."""
    payload = _meta_request(
        "POST",
        f"{IG_USER_ID}/media",
        {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": IG_ACCESS_TOKEN,
        },
    )
    container_id = payload.get("id")
    if not container_id:
        raise InstagramPublishError(f"Carousel item container creation failed: {payload}")
    return container_id


def _create_carousel_container(caption: str, children_ids: list[str]) -> str:
    """Creates the parent CAROUSEL container linking all item containers."""
    payload = _meta_request(
        "POST",
        f"{IG_USER_ID}/media",
        {
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(children_ids),
            "access_token": IG_ACCESS_TOKEN,
        },
    )
    container_id = payload.get("id")
    if not container_id:
        raise InstagramPublishError(f"Carousel container creation failed: {payload}")
    return container_id


def _publish_carousel_live(caption: str, image_urls: list[str]) -> dict:
    _require_live_credentials()

    item_ids = []
    for url in image_urls:
        item_id = _create_carousel_item_container(url)
        _wait_for_container_ready(item_id)
        item_ids.append(item_id)

    parent_id = _create_carousel_container(caption, item_ids)
    _wait_for_container_ready(parent_id)
    media_id = _publish_media_container(parent_id)

    return {
        "success": True,
        "mode": "live",
        "status": "published",
        "message": f"Instagram carousel ({len(image_urls)} slides) published successfully.",
        "media_id": media_id,
        "caption": caption,
        "image_urls": image_urls,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def publish_carousel_post(caption: str, image_urls: list[str]) -> dict:
    """Phase 16 (carousel feature) -- publishes a multi-image
    carousel/slideshow post. In mock mode, simulates success the same
    way publish_post() does, without contacting Instagram."""
    if not image_urls:
        raise InstagramPublishError("Carousel post needs at least one image URL.")
    validate_post(caption, image_urls[0])

    if PUBLISH_MODE == "mock":
        return {
            "success": True,
            "mode": "mock",
            "status": "simulated",
            "message": f"Instagram carousel ({len(image_urls)} slides) simulated successfully.",
            "media_id": None,
            "caption": caption,
            "image_urls": image_urls,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    if PUBLISH_MODE != "live":
        raise InstagramPublishError(
            f"Unsupported PUBLISH_MODE: {PUBLISH_MODE}. Use 'mock' or 'live'."
        )

    return _publish_carousel_live(caption, image_urls)


def _publish_post_live(caption: str, image_url: str) -> dict:
    _require_live_credentials()

    container_id = _create_media_container(caption, image_url)
    _wait_for_container_ready(container_id)
    media_id = _publish_media_container(container_id)

    return {
        "success": True,
        "mode": "live",
        "status": "published",
        "message": "Instagram post published successfully.",
        "media_id": media_id,
        "container_id": container_id,
        "caption": caption,
        "image_url": image_url,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def publish_post(caption: str, image_url: str) -> dict:
    """
    Publish an Instagram post.

    In mock mode this does not contact Instagram — it returns a
    simulated successful result (Phase 9 behavior, unchanged).

    In live mode this performs the real two-step Graph API publish
    (Phase 13). image_url MUST be a public HTTPS URL — a local file
    path will fail, since Instagram fetches it directly.
    """

    validate_post(caption, image_url)

    if PUBLISH_MODE == "mock":
        return {
            "success": True,
            "mode": "mock",
            "status": "simulated",
            "message": "Instagram post simulated successfully.",
            "media_id": None,
            "caption": caption,
            "image_url": image_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    if PUBLISH_MODE != "live":
        raise InstagramPublishError(
            f"Unsupported PUBLISH_MODE: {PUBLISH_MODE}. Use 'mock' or 'live'."
        )

    return _publish_post_live(caption, image_url)


def get_publish_mode() -> str:
    """Return the current publishing mode."""

    return PUBLISH_MODE


if __name__ == "__main__":
    print(f"Instagram publishing mode: {PUBLISH_MODE}")

    if PUBLISH_MODE == "mock":
        result = publish_post(
            caption="Test post from Nichely.",
            image_url="https://example.com/test-image.jpg",
        )

        print(result)
    else:
        print(
            "PUBLISH_MODE=live — run this against a real pending post via "
            "app.py or pipeline.py instead of this smoke test, since a "
            "live run needs a real public image_url and will actually post."
        )