"""
Cloud image hosting — Phase 13 support.

Instagram's Graph API publishing endpoints require a *publicly
reachable* image URL — they cannot read a local file path. Posters are
rendered locally by services/poster_service.py (Phase 7), so before a
real (live) publish, the poster needs to be uploaded somewhere public
first. This module uploads to Cloudinary, configured entirely from the
CLOUDINARY_URL environment variable (see .env.example).

If CLOUDINARY_URL isn't set, uploads simply fail with a clear error —
this is fine in mock mode, where no public URL is actually needed.
"""

import os

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")

_configured = False


class CloudUploadError(RuntimeError):
    """Raised when a poster image cannot be uploaded to public hosting."""


def _ensure_configured() -> None:
    """Cloudinary's SDK auto-reads CLOUDINARY_URL from the environment,
    but only if it's set before the first config lookup — this makes
    sure load_dotenv() has already run and gives a clear error early
    if the variable is simply missing, instead of a confusing SDK error
    later."""
    global _configured

    if _configured:
        return

    if not CLOUDINARY_URL:
        raise CloudUploadError(
            "CLOUDINARY_URL is not set. Add it to your .env file "
            "(sign up free at cloudinary.com, then copy the "
            "'API Environment variable' value) before using live "
            "publishing — Instagram needs a public image URL."
        )

    cloudinary.config(cloudinary_url=CLOUDINARY_URL)
    _configured = True


def upload_image(local_path: str, public_id: str | None = None) -> str:
    """Uploads a local image file and returns its public HTTPS URL.

    Parameters:
        local_path: path to the rendered poster JPEG on disk.
        public_id: optional stable identifier (e.g. the Post id) so
            re-uploading the same post overwrites rather than
            accumulating duplicates in the Cloudinary media library.
    """

    if not local_path or not os.path.isfile(local_path):
        raise CloudUploadError(f"Poster file not found: {local_path}")

    _ensure_configured()

    try:
        result = cloudinary.uploader.upload(
            local_path,
            folder="nichely_posters",
            public_id=public_id,
            overwrite=True,
            resource_type="image",
        )
    except Exception as exc:  # cloudinary raises its own error types
        raise CloudUploadError(f"Cloudinary upload failed: {exc}") from exc

    secure_url = result.get("secure_url")
    if not secure_url:
        raise CloudUploadError("Cloudinary upload succeeded but returned no secure_url.")

    return secure_url


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m services.cloud_upload_service <path-to-image>")
    else:
        try:
            url = upload_image(sys.argv[1])
            print(f"Uploaded. Public URL: {url}")
        except CloudUploadError as exc:
            print(f"Upload failed: {exc}")
