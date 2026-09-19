"""
Source reliability service — rule-based, no LLM involved (see spec §6).

This is intentionally the simplest possible implementation: a fixed
allowlist lookup by domain. This is a deliberate design choice, not a
placeholder — reliability scoring should be auditable and stable, which
a lookup table gives you and an LLM "vibe check" would not.
"""

from config import SOURCE_RELIABILITY_TIERS, DEFAULT_RELIABILITY_TIER
from utils.text_cleaning import extract_domain


def get_reliability_tier(url: str) -> float:
    domain = extract_domain(url)
    return SOURCE_RELIABILITY_TIERS.get(domain, DEFAULT_RELIABILITY_TIER)
