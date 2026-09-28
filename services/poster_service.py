"""
Poster service — Phase 7 + carousel feature.

Phase 7:
    Generates a background image using Hugging Face SDXL,
    then overlays the headline and branding.

Carousel:
    Reuses the already-generated poster image.
    Different text is placed on each slide locally using Pillow.
    This means carousel generation does NOT call Hugging Face again.
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont
from huggingface_hub import InferenceClient

from config import POSTER_WIDTH, POSTER_HEIGHT, POSTER_OUTPUT_DIR
from database.db import get_session
from database.models import Post
from services.cloud_upload_service import (
    upload_image,
    CloudUploadError,
)


# ---------------------------------------------------------------------------
# Hugging Face configuration
# ---------------------------------------------------------------------------

HF_TOKEN = os.getenv("HF_TOKEN")

IMAGE_MODEL_NAME = "stabilityai/stable-diffusion-xl-base-1.0"


# ---------------------------------------------------------------------------
# Background image generation
# ---------------------------------------------------------------------------

def generate_background_image(image_description: str) -> Image.Image:
    """
    Generate the background image for the main poster using Hugging Face.

    NOTE:
    This is used for the FIRST/main poster only.

    Carousel generation does NOT call this function.
    """

    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN is not set. Add it to your .env file before running this."
        )

    client = InferenceClient(token=HF_TOKEN)

    prompt = (
        "A high-quality, cinematic photo for an entertainment news poster: "
        f"{image_description}. "
        "Vibrant, glossy, magazine-style lighting. "
        "Square composition, no text, no logos, no watermarks."
    )

    return client.text_to_image(
        prompt,
        model=IMAGE_MODEL_NAME,
    )


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------

_FONT_CANDIDATES_REGULAR = [
    "DejaVuSans.ttf",
    "Arial.ttf",
    "arial.ttf",
]

_FONT_CANDIDATES_BOLD = [
    "DejaVuSans-Bold.ttf",
    "Arial-Bold.ttf",
    "arialbd.ttf",
]


def _load_font(size: int, bold: bool = False):
    """
    Try common fonts before falling back to PIL's default font.
    """

    candidates = (
        _FONT_CANDIDATES_BOLD
        if bold
        else _FONT_CANDIDATES_REGULAR
    )

    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Shared slide renderer (used by the main poster AND every carousel slide)
# ---------------------------------------------------------------------------

def _background_path(post_id: str) -> str:
    """Where the CLEAN (text-free) square background for a post is kept.

    The carousel draws each slide's text on this file instead of on the
    finished poster, so there is never any old headline to cover up.
    """
    return os.path.join(POSTER_OUTPUT_DIR, f"{post_id}_bg.jpg")


def _prepare_square_background(background_image: Image.Image) -> Image.Image:
    """Centre-crop to a square and resize to poster size. No text added."""

    image = background_image.convert("RGB")

    w, h = image.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2

    return image.crop(
        (left, top, left + side, top + side)
    ).resize(
        (POSTER_WIDTH, POSTER_HEIGHT)
    )


def _draw_slide(
    background: Image.Image,
    text: str,
    font_size: int = 72,
    line_height: int = 82,
) -> Image.Image:
    """
    Draw the brand tag and `text` directly on top of `background`.

    Legibility comes from a soft, transparent-to-dark gradient over the
    bottom 55% of the image, so the photo stays visible behind the text
    (no solid black panel).
    """

    if background.size != (POSTER_WIDTH, POSTER_HEIGHT):
        background = background.resize((POSTER_WIDTH, POSTER_HEIGHT))

    image = background.convert("RGBA")

    # -- soft gradient behind the text --------------------------------
    gradient_height = int(POSTER_HEIGHT * 0.55)

    gradient = Image.new("RGBA", (1, gradient_height), color=0)

    for y in range(gradient_height):
        alpha = int(230 * (y / gradient_height) ** 1.6)
        gradient.putpixel((0, y), (0, 0, 0, alpha))

    gradient = gradient.resize((POSTER_WIDTH, gradient_height))

    region_top = POSTER_HEIGHT - gradient_height

    image.paste(
        Image.alpha_composite(
            image.crop((0, region_top, POSTER_WIDTH, POSTER_HEIGHT)),
            gradient,
        ),
        (0, region_top),
    )

    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)

    # -- brand tag ------------------------------------------------------
    tag_font = _load_font(32)
    tag_text = "ENTERTAINMENT"

    tag_padding_x = 22
    tag_padding_y = 12

    tag_width = draw.textlength(tag_text, font=tag_font) + tag_padding_x * 2
    tag_height = 32 + tag_padding_y * 2

    tag_x = 40
    tag_y = 40

    draw.rounded_rectangle(
        [(tag_x, tag_y), (tag_x + tag_width, tag_y + tag_height)],
        radius=tag_height // 2,
        fill=(230, 30, 60),
    )

    draw.text(
        (tag_x + tag_padding_x, tag_y + tag_padding_y - 2),
        tag_text,
        font=tag_font,
        fill="white",
    )

    # -- wrapped, bottom-anchored text -----------------------------------
    text_font = _load_font(font_size, bold=True)
    max_width = POSTER_WIDTH - 100

    lines = []
    current = ""

    for word in text.upper().split():
        trial = f"{current} {word}".strip()

        if draw.textlength(trial, font=text_font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    y = POSTER_HEIGHT - 60 - line_height * len(lines)

    for line in lines:
        text_width = draw.textlength(line, font=text_font)
        x = (POSTER_WIDTH - text_width) // 2

        # shadow, then main text
        draw.text((x + 4, y + 4), line, font=text_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=text_font, fill="white")

        y += line_height

    return image


def render_poster(
    background_image: Image.Image,
    headline: str,
    output_path: str,
) -> str:
    """
    Overlay the headline and branding on a background image.
    """

    square = _prepare_square_background(background_image)
    image = _draw_slide(square, headline, font_size=72, line_height=82)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    image.save(output_path, "JPEG", quality=92)

    return output_path


# ---------------------------------------------------------------------------
# Generate MAIN poster
# ---------------------------------------------------------------------------

def generate_poster_for_latest_pending_post() -> str | None:
    """
    Find the most recent pending post without a poster.

    Generates the main poster using Hugging Face,
    saves it locally, and attempts to upload it to Cloudinary.
    """

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.approval_status == "pending"
            )
            .filter(
                Post.poster_local_path.is_(None)
            )
            .order_by(
                Post.created_at.desc()
            )
            .first()
        )

        if post is None:
            return None

        headline = post.headline

        image_description = (
            post.poster_image_description
            or headline
        )

        post_id = post.id

    # ---------------------------------------------------------------
    # Generate AI background
    # ---------------------------------------------------------------

    background = generate_background_image(
        image_description
    )

    # ---------------------------------------------------------------
    # Output path
    # ---------------------------------------------------------------

    output_path = os.path.join(
        POSTER_OUTPUT_DIR,
        f"{post_id}.jpg",
    )

    # ---------------------------------------------------------------
    # Render poster
    # ---------------------------------------------------------------

    # Keep a clean (text-free) copy of the background so carousel slides
    # can be drawn on it later without any old headline showing through.
    os.makedirs(POSTER_OUTPUT_DIR, exist_ok=True)
    _prepare_square_background(background).save(
        _background_path(post_id),
        "JPEG",
        quality=95,
    )

    render_poster(
        background,
        headline,
        output_path,
    )

    # ---------------------------------------------------------------
    # Save local path
    # ---------------------------------------------------------------

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        post.poster_local_path = output_path

    # ---------------------------------------------------------------
    # Upload to Cloudinary if configured
    # ---------------------------------------------------------------

    try:

        ensure_public_url_for_post(
            post_id
        )

    except CloudUploadError as exc:

        print(
            "Note: poster saved locally, "
            "but public upload was skipped "
            f"({exc})"
        )

    return output_path


# ---------------------------------------------------------------------------
# CAROUSEL GENERATION
# ---------------------------------------------------------------------------

def _cover_baked_headline(poster: Image.Image) -> Image.Image:
    """
    LEGACY fallback, only used for posts made before clean backgrounds were
    saved. The finished poster already has its headline baked in, so the
    bottom of the image is covered with a near-solid dark gradient to hide
    it. This is what produces the big black block -- regenerate the poster
    for that post to get proper transparent captions.
    """

    image = poster.convert("RGBA")

    overlay_top = int(image.height * 0.52)
    gradient_height = image.height - overlay_top
    fade_zone = int(gradient_height * 0.15)

    gradient = Image.new("RGBA", (1, gradient_height), color=0)

    for gy in range(gradient_height):
        alpha = int(245 * (gy / fade_zone)) if gy < fade_zone else 245
        gradient.putpixel((0, gy), (0, 0, 0, alpha))

    gradient = gradient.resize((image.width, gradient_height))

    image.paste(
        Image.alpha_composite(
            image.crop((0, overlay_top, image.width, image.height)),
            gradient,
        ),
        (0, overlay_top),
    )

    return image.convert("RGB")


def generate_carousel_for_post(
    post_id: str,
) -> list[str]:
    """
    Generate carousel slides WITHOUT generating new AI images.

    Each slide is the post's CLEAN background (saved as <post_id>_bg.jpg
    when the poster was generated) with that slide's text drawn directly on
    top, using the same soft gradient as the main poster.

        Slide 1: main headline
        Slide 2..n: supporting details from carousel_slides_json

    No Hugging Face call is made here.
    """

    # ---------------------------------------------------------------
    # Get post
    # ---------------------------------------------------------------

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(Post.id == post_id)
            .one()
        )

        headline = post.headline

        extra_slides = json.loads(
            post.carousel_slides_json or "[]"
        )

        existing_poster_path = post.poster_local_path

    # ---------------------------------------------------------------
    # Validate poster
    # ---------------------------------------------------------------

    if not existing_poster_path:
        raise RuntimeError(
            "Cannot create carousel because this post "
            "does not have a poster yet. "
            "Generate the poster first."
        )

    # ---------------------------------------------------------------
    # Pick the base image every slide is drawn on
    # ---------------------------------------------------------------

    bg_path = _background_path(post_id)

    if os.path.exists(bg_path):

        base = Image.open(bg_path).convert("RGB")

    else:

        if not os.path.exists(existing_poster_path):
            raise RuntimeError(
                "Existing poster file was not found: "
                f"{existing_poster_path}"
            )

        print(
            "Note: no clean background saved for this post "
            "(it was created before that was added), so the old "
            "headline has to be covered with a dark panel. "
            "Regenerate the poster to get captions directly on the image."
        )

        base = _cover_baked_headline(
            Image.open(existing_poster_path).convert("RGB").resize(
                (POSTER_WIDTH, POSTER_HEIGHT)
            )
        )

    # ---------------------------------------------------------------
    # Create each slide
    # ---------------------------------------------------------------

    slide_texts = [headline] + extra_slides

    paths = []

    for i, text in enumerate(slide_texts):

        output_path = os.path.join(
            POSTER_OUTPUT_DIR,
            f"{post_id}_{i}.jpg",
        )

        image = _draw_slide(
            base,
            text,
            font_size=58,
            line_height=66,
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        image.save(output_path, "JPEG", quality=92)

        paths.append(output_path)

    # ---------------------------------------------------------------
    # Save carousel paths in database
    # ---------------------------------------------------------------

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(Post.id == post_id)
            .one()
        )

        post.poster_local_paths = json.dumps(paths)

    return paths


# ---------------------------------------------------------------------------
# Upload carousel slides to Cloudinary
# ---------------------------------------------------------------------------

def ensure_public_urls_for_carousel(
    post_id: str,
) -> list[str]:
    """
    Upload every carousel slide to Cloudinary
    and return public HTTPS URLs.
    """

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        if post.poster_public_urls:

            return json.loads(
                post.poster_public_urls
            )

        local_paths = json.loads(
            post.poster_local_paths
            or "[]"
        )

    if not local_paths:

        raise CloudUploadError(
            f"Post {post_id} has no carousel slides "
            "to upload yet."
        )

    # Upload every slide

    urls = [
        upload_image(
            path,
            public_id=f"{post_id}_{i}",
        )
        for i, path in enumerate(
            local_paths
        )
    ]

    # Save URLs

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        post.poster_public_urls = json.dumps(
            urls
        )

    return urls


# ---------------------------------------------------------------------------
# Upload main poster to Cloudinary
# ---------------------------------------------------------------------------

def ensure_public_url_for_post(
    post_id: str,
) -> str:
    """
    Upload the main poster to Cloudinary if it doesn't
    already have a public URL.
    """

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        if post.poster_public_url:

            return post.poster_public_url

        local_path = post.poster_local_path

    if not local_path:

        raise CloudUploadError(
            f"Post {post_id} has no local poster "
            "to upload yet."
        )

    public_url = upload_image(
        local_path,
        public_id=post_id,
    )

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        post.poster_public_url = public_url

    return public_url


# ---------------------------------------------------------------------------
# Command-line test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    result = (
        generate_poster_for_latest_pending_post()
    )

    if result:

        print(
            f"Poster saved to: {result}"
        )

    else:

        print(
            "No pending post without a poster found — "
            "run Phase 6 (content_strategist) first."
        )