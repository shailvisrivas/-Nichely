"""
Retry wrapper for Gemini API calls.

gemini-3.6-flash has a documented intermittent high-demand issue (~37%
failure rate reported by other developers, not a permanent outage) —
most calls succeed within a few retries, so this wraps
generate_content with backoff instead of letting one unlucky call
crash the whole pipeline run.
"""

import time
from google.genai.errors import ServerError


def generate_with_retry(client, model, contents, max_retries=10, base_delay=2):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except ServerError:
            if attempt == max_retries - 1:
                raise
            wait = base_delay * (attempt + 1)
            print(f"Gemini 503 (attempt {attempt + 1}/{max_retries}) — retrying in {wait}s...")
            time.sleep(wait)