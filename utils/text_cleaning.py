"""
Text cleaning helpers for raw article content coming back from the news API.

Kept deliberately simple and dependency-free (no HTML parsing library) —
news API responses are typically already plain text or lightly-tagged,
so a couple of regex passes are enough for this project's needs.
"""

import re


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text)


def collapse_whitespace(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_chars: int = 4000) -> str:
    if not text:
        return ""
    return text[:max_chars]


def clean_article_text(raw_text: str, max_chars: int = 4000) -> str:
    """Full cleaning pipeline for one article's body text."""
    text = strip_html(raw_text or "")
    text = collapse_whitespace(text)
    text = truncate(text, max_chars)
    return text


def extract_domain(url: str) -> str:
    """Pulls 'techcrunch.com' out of 'https://www.techcrunch.com/2026/...'."""
    if not url:
        return ""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1).lower() if match else ""
