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
# Main poster renderer
# ---------------------------------------------------------------------------

def render_poster(
    background_image: Image.Image,
    headline: str,
    output_path: str,
) -> str:
    """
    Overlay the headline and branding on a background image.
    """

    # ---------------------------------------------------------------
    # Center crop to square
    # ---------------------------------------------------------------

    w, h = background_image.size

    side = min(w, h)

    left = (w - side) // 2
    top = (h - side) // 2

    image = background_image.crop(
        (
            left,
            top,
            left + side,
            top + side,
        )
    ).resize(
        (
            POSTER_WIDTH,
            POSTER_HEIGHT,
        )
    )

    image = image.convert("RGBA")

    # ---------------------------------------------------------------
    # Gradient behind headline
    # ---------------------------------------------------------------

    gradient_height = int(
        POSTER_HEIGHT * 0.55
    )

    gradient = Image.new(
        "RGBA",
        (
            1,
            gradient_height,
        ),
        color=0,
    )

    for y in range(gradient_height):

        alpha = int(
            230
            * (y / gradient_height) ** 1.6
        )

        gradient.putpixel(
            (
                0,
                y,
            ),
            (
                0,
                0,
                0,
                alpha,
            ),
        )

    gradient = gradient.resize(
        (
            POSTER_WIDTH,
            gradient_height,
        )
    )

    image.paste(
        Image.alpha_composite(
            image.crop(
                (
                    0,
                    POSTER_HEIGHT - gradient_height,
                    POSTER_WIDTH,
                    POSTER_HEIGHT,
                )
            ),
            gradient,
        ),
        (
            0,
            POSTER_HEIGHT - gradient_height,
        ),
    )

    image = image.convert("RGB")

    draw = ImageDraw.Draw(image)

    # ---------------------------------------------------------------
    # Brand tag
    # ---------------------------------------------------------------

    tag_font = _load_font(
        32
    )

    tag_text = "ENTERTAINMENT"

    tag_padding_x = 22
    tag_padding_y = 12

    tag_width = (
        draw.textlength(
            tag_text,
            font=tag_font,
        )
        + tag_padding_x * 2
    )

    tag_height = (
        32
        + tag_padding_y * 2
    )

    tag_x = 40
    tag_y = 40

    draw.rounded_rectangle(
        [
            (
                tag_x,
                tag_y,
            ),
            (
                tag_x + tag_width,
                tag_y + tag_height,
            ),
        ],
        radius=tag_height // 2,
        fill=(230, 30, 60),
    )

    draw.text(
        (
            tag_x + tag_padding_x,
            tag_y + tag_padding_y - 2,
        ),
        tag_text,
        font=tag_font,
        fill="white",
    )

    # ---------------------------------------------------------------
    # Headline
    # ---------------------------------------------------------------

    headline_font = _load_font(
        72,
        bold=True,
    )

    max_width = (
        POSTER_WIDTH - 100
    )

    words = headline.upper().split()

    lines = []

    current = ""

    for word in words:

        trial = (
            f"{current} {word}"
        ).strip()

        if draw.textlength(
            trial,
            font=headline_font,
        ) <= max_width:

            current = trial

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    line_height = 82

    text_block_height = (
        line_height
        * len(lines)
    )

    y = (
        POSTER_HEIGHT
        - 60
        - text_block_height
    )

    for line in lines:

        text_width = draw.textlength(
            line,
            font=headline_font,
        )

        x = (
            POSTER_WIDTH
            - text_width
        ) // 2

        # Shadow
        draw.text(
            (
                x + 4,
                y + 4,
            ),
            line,
            font=headline_font,
            fill=(0, 0, 0),
        )

        # Main text
        draw.text(
            (
                x,
                y,
            ),
            line,
            font=headline_font,
            fill="white",
        )

        y += line_height

    # ---------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True,
    )

    image.save(
        output_path,
        "JPEG",
        quality=92,
    )

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

def generate_carousel_for_post(
    post_id: str,
) -> list[str]:
    """
    Generate carousel slides WITHOUT generating new AI images.

    IMPORTANT:
        The existing main poster is reused as the background.

    Example:

        Slide 1:
            Main headline

        Slide 2:
            Supporting detail #1

        Slide 3:
            Supporting detail #2

        Slide 4:
            Supporting detail #3

    The text changes between slides but the underlying image remains
    the same.

    No Hugging Face image-generation call is made here.
    """

    # ---------------------------------------------------------------
    # Get post
    # ---------------------------------------------------------------

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        headline = post.headline

        extra_slides = json.loads(
            post.carousel_slides_json
            or "[]"
        )

        existing_poster_path = (
            post.poster_local_path
        )

    # ---------------------------------------------------------------
    # Validate poster
    # ---------------------------------------------------------------

    if not existing_poster_path:

        raise RuntimeError(
            "Cannot create carousel because this post "
            "does not have a poster yet. "
            "Generate the poster first."
        )

    if not os.path.exists(
        existing_poster_path
    ):

        raise RuntimeError(
            "Existing poster file was not found: "
            f"{existing_poster_path}"
        )

    # ---------------------------------------------------------------
    # Slide content
    # ---------------------------------------------------------------

    slide_texts = [
        headline
    ] + extra_slides

    paths = []

    # ---------------------------------------------------------------
    # Create each slide
    # ---------------------------------------------------------------

    for i, text in enumerate(
        slide_texts
    ):

        output_path = os.path.join(
            POSTER_OUTPUT_DIR,
            f"{post_id}_{i}.jpg",
        )

        # -----------------------------------------------------------
        # IMPORTANT:
        # Reuse the SAME existing poster.
        # NO Hugging Face call.
        # -----------------------------------------------------------

        image = Image.open(
            existing_poster_path
        ).convert("RGB")

        # Make sure carousel image has the correct dimensions.

        image = image.resize(
            (
                POSTER_WIDTH,
                POSTER_HEIGHT,
            )
        )

        draw = ImageDraw.Draw(
            image
        )

        # -----------------------------------------------------------
        # Cover the old headline area
        # -----------------------------------------------------------

        overlay_top = int(
            image.height * 0.55
        )

        draw.rectangle(
            [
                (
                    0,
                    overlay_top,
                ),
                (
                    image.width,
                    image.height,
                ),
            ],
            fill=(0, 0, 0),
        )

        # -----------------------------------------------------------
        # Brand tag
        # -----------------------------------------------------------

        tag_font = _load_font(
            32
        )

        tag_text = "ENTERTAINMENT"

        tag_padding_x = 22
        tag_padding_y = 12

        tag_width = (
            draw.textlength(
                tag_text,
                font=tag_font,
            )
            + tag_padding_x * 2
        )

        tag_height = (
            32
            + tag_padding_y * 2
        )

        tag_x = 40
        tag_y = 40

        draw.rounded_rectangle(
            [
                (
                    tag_x,
                    tag_y,
                ),
                (
                    tag_x + tag_width,
                    tag_y + tag_height,
                ),
            ],
            radius=tag_height // 2,
            fill=(230, 30, 60),
        )

        draw.text(
            (
                tag_x + tag_padding_x,
                tag_y + tag_padding_y - 2,
            ),
            tag_text,
            font=tag_font,
            fill="white",
        )

        # -----------------------------------------------------------
        # Slide text
        # -----------------------------------------------------------

        headline_font = _load_font(
            68,
            bold=True,
        )

        max_width = (
            image.width - 100
        )

        words = text.upper().split()

        lines = []

        current = ""

        for word in words:

            trial = (
                f"{current} {word}"
            ).strip()

            if draw.textlength(
                trial,
                font=headline_font,
            ) <= max_width:

                current = trial

            else:

                if current:
                    lines.append(
                        current
                    )

                current = word

        if current:
            lines.append(
                current
            )

        # -----------------------------------------------------------
        # Position text
        # -----------------------------------------------------------

        line_height = 78

        text_block_height = (
            line_height
            * len(lines)
        )

        y = (
            image.height
            - 70
            - text_block_height
        )

        # -----------------------------------------------------------
        # Draw text
        # -----------------------------------------------------------

        for line in lines:

            text_width = draw.textlength(
                line,
                font=headline_font,
            )

            x = (
                image.width
                - text_width
            ) // 2

            # Shadow
            draw.text(
                (
                    x + 4,
                    y + 4,
                ),
                line,
                font=headline_font,
                fill=(0, 0, 0),
            )

            # Main text
            draw.text(
                (
                    x,
                    y,
                ),
                line,
                font=headline_font,
                fill="white",
            )

            y += line_height

        # -----------------------------------------------------------
        # Save slide
        # -----------------------------------------------------------

        os.makedirs(
            os.path.dirname(
                output_path
            ),
            exist_ok=True,
        )

        image.save(
            output_path,
            "JPEG",
            quality=92,
        )

        paths.append(
            output_path
        )

    # ---------------------------------------------------------------
    # Save carousel paths in database
    # ---------------------------------------------------------------

    with get_session() as session:

        post = (
            session.query(Post)
            .filter(
                Post.id == post_id
            )
            .one()
        )

        post.poster_local_paths = json.dumps(
            paths
        )

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