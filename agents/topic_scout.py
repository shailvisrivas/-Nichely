"""
Phase 5 — Topic Scout Agent.

Reads the clustered, relevance-filtered articles Phase 4 already stored
(grouped by `story_cluster_id`), scores each cluster on five factors, asks
Gemini to fill in the two judgement-heavy factors (novelty, audience
interest) plus a written rationale, combines everything with the current
active scoring weights, and writes a ranked result into `topics_considered`.

Deterministic scores (plain Python, no LLM needed):
  - score_recency     : time-decay based on the newest article in the cluster
  - score_relevance   : cosine similarity between the cluster's embedding
                        and the niche description's embedding
  - score_reliability : average `reliability_tier` across the cluster's
                        source articles

Judgement-heavy scores from one batched Gemini call:
  - score_novelty     : is this a fresh angle, or an already-done-to-death story?
  - score_audience    : rough proxy for audience interest (not a performance guarantee)

Also returns a written reasoning_text per candidate and an overall
explanation for the top pick — this is what you show your professor when
they ask "why did the AI pick this?"

Usage:python -m agents.topic_scout
    
"""

import json
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL_NAME, NICHE_DESCRIPTION, MAX_ARTICLE_AGE_HOURS
from database.db import get_session, init_db, get_active_weights
from database.models import SourceArticle, TopicConsidered
from services.embedding_service import embed_text, embedding_from_json, cosine_similarity


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _hours_since(iso_timestamp: str) -> float:
    published = datetime.fromisoformat(iso_timestamp)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - published).total_seconds() / 3600.0


def _recency_score(hours_old: float) -> float:
    """Linear decay to 0 at MAX_ARTICLE_AGE_HOURS, clamped to [0, 1]."""
    return max(0.0, min(1.0, 1.0 - (hours_old / MAX_ARTICLE_AGE_HOURS)))


def build_candidates() -> list[dict]:
    """Groups Phase 4's clustered articles by story_cluster_id and computes
    the three deterministic scores for each cluster."""
    niche_vector = np.array(embed_text(NICHE_DESCRIPTION), dtype=np.float32)

    with get_session() as session:
        articles = (
            session.query(SourceArticle)
            .filter(SourceArticle.story_cluster_id.isnot(None))
            .all()
        )

        clusters: dict[str, list[SourceArticle]] = defaultdict(list)
        for a in articles:
            clusters[a.story_cluster_id].append(a)

        candidates = []
        for cluster_id, members in clusters.items():
            members.sort(key=lambda a: a.published_at, reverse=True)
            lead = members[0]

            hours_old = _hours_since(lead.published_at)
            if hours_old > MAX_ARTICLE_AGE_HOURS:
                continue

            vectors = [embedding_from_json(a.embedding) for a in members if a.embedding]
            cluster_vector = np.mean(vectors, axis=0) if vectors else niche_vector

            candidates.append({
                "cluster_id": cluster_id,
                "headline_candidate": lead.title,
                "source_article_ids": [a.id for a in members],
                "source_names": sorted(set(a.source_name for a in members)),
                "corroboration_count": len(members),
                "snippet": lead.body_text[:600],
                "score_recency": round(_recency_score(hours_old), 3),
                "score_relevance": round(cosine_similarity(cluster_vector, niche_vector), 3),
                "score_reliability": round(
                    sum(a.reliability_tier for a in members) / len(members), 3
                ),
            })

    return candidates


# ---------------------------------------------------------------------------
# Gemini call — novelty, audience interest, reasoning
# ---------------------------------------------------------------------------

SCOUT_PROMPT_TEMPLATE = """You are helping select ONE story for a Bollywood & Hollywood entertainment Instagram page to post about today.

For each candidate below, assign two scores from 0.0 to 1.0:
- "novelty": is this a fresh angle, or an already-done-to-death story? (1.0 = very fresh/original, 0.0 = extremely overdone/stale)
- "audience_interest": your best estimate of general entertainment-audience interest in this specific story (1.0 = very high interest, 0.0 = niche/low interest). This is a rough proxy signal, not a guarantee.

Also write a one-sentence "reasoning" for each candidate explaining your scores.

Then pick the single best candidate overall (considering ALL five scores I've given you, not just the two you're assigning) and write a 2-3 sentence "overall_reasoning" explaining why it's the best choice to post about right now, referencing specific numbers.

Candidates:
{candidates_json}

Respond with ONLY valid JSON, no markdown fences, no preamble, in exactly this shape:
{{
  "scored_candidates": [
    {{"cluster_id": "...", "novelty": 0.0, "audience_interest": 0.0, "reasoning": "..."}}
  ],
  "best_cluster_id": "...",
  "overall_reasoning": "..."
}}
"""


def score_with_gemini(candidates: list[dict]) -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)

    slim = [
        {
            "cluster_id": c["cluster_id"],
            "headline": c["headline_candidate"],
            "snippet": c["snippet"],
            "score_recency": c["score_recency"],
            "score_relevance": c["score_relevance"],
            "score_reliability": c["score_reliability"],
            "corroboration_count": c["corroboration_count"],
        }
        for c in candidates
    ]

    prompt = SCOUT_PROMPT_TEMPLATE.format(candidates_json=json.dumps(slim, indent=2))
    response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=prompt)

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").replace("json\n", "", 1)

    return json.loads(raw_text)


# ---------------------------------------------------------------------------
# Combine, rank, write to DB
# ---------------------------------------------------------------------------

def run_topic_scout():
    init_db()  # also seeds default weights if missing (her logic)

    candidates = build_candidates()
    if not candidates:
        print("No eligible candidate stories found (all filtered out or too old).")
        return

    weights = get_active_weights()
    gemini_result = score_with_gemini(candidates)
    gemini_by_cluster = {c["cluster_id"]: c for c in gemini_result["scored_candidates"]}

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    ranked = []

    for c in candidates:
        gem = gemini_by_cluster.get(c["cluster_id"], {})
        novelty = gem.get("novelty", 0.0)
        audience = gem.get("audience_interest", 0.0)

        final_score = (
            weights["w_recency"] * c["score_recency"]
            + weights["w_relevance"] * c["score_relevance"]
            + weights["w_reliability"] * c["score_reliability"]
            + weights["w_novelty"] * novelty
            + weights["w_audience"] * audience
        )

        ranked.append({
            **c,
            "score_novelty": novelty,
            "score_audience": audience,
            "final_score": round(final_score, 4),
            "per_candidate_reasoning": gem.get("reasoning", ""),
        })

    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    best_cluster_id = gemini_result.get("best_cluster_id", ranked[0]["cluster_id"])

    with get_session() as session:
        for i, c in enumerate(ranked):
            if c["cluster_id"] == best_cluster_id:
                status = "selected"
                reasoning = gemini_result.get("overall_reasoning", c["per_candidate_reasoning"])
            elif i < 5:
                status = "shortlisted"
                reasoning = c["per_candidate_reasoning"]
            else:
                status = "rejected"
                reasoning = c["per_candidate_reasoning"] or "Ranked below shortlist cutoff."

            session.merge(TopicConsidered(
                id=c["cluster_id"],
                run_id=run_id,
                headline_candidate=c["headline_candidate"],
                source_article_ids=json.dumps(c["source_article_ids"]),
                score_recency=c["score_recency"],
                score_relevance=c["score_relevance"],
                score_reliability=c["score_reliability"],
                score_novelty=c["score_novelty"],
                score_audience=c["score_audience"],
                final_score=c["final_score"],
                status=status,
                rejection_reason=None if status != "rejected" else reasoning,
                reasoning_text=reasoning,
            ))
        # get_session()'s context manager commits automatically on clean exit

    print(f"\nRun {run_id} — {len(ranked)} candidate stories evaluated\n")
    for i, c in enumerate(ranked[:5], start=1):
        marker = " <-- SELECTED" if c["cluster_id"] == best_cluster_id else ""
        print(f"{i}. [{c['final_score']:.3f}] {c['headline_candidate']}{marker}")
        print(f"   recency={c['score_recency']} relevance={c['score_relevance']} "
              f"reliability={c['score_reliability']} novelty={c['score_novelty']} "
              f"audience={c['score_audience']} | sources: {', '.join(c['source_names'])}")
    print(f"\nWhy this one: {gemini_result.get('overall_reasoning')}\n")


if __name__ == "__main__":
    run_topic_scout()
