"""
Phase 6 — Content Strategist Agent.

Takes a topic from `topics_considered` — by default the one Phase 5
marked "selected", but you can instead pass a specific topic_id (e.g. to
use a "shortlisted" one instead) — pulls the real source article text it
was based on, and asks Gemini to write the actual Instagram content:
headline, caption, hashtags, a call-to-action, the main public figure
named in the story (if any), and a description of what the poster image
should show.

Grounding: the prompt includes the real article text and explicitly
instructs the model not to state anything that isn't traceable to it —
this is the RAG-style grounding from the spec, meant to stop the caption
from inventing facts.

Also supports regeneration with human feedback (e.g. from a rejected
post in the Streamlit approval screen) — the feedback is added to the
prompt so the new version specifically addresses what was wrong with
the last one.

CLI usage:python -m agents.content_strategist
    -> lists the selected + shortlisted topics from the latest run and
       lets you pick one (press Enter for the auto-selected one).
"""

import json

from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL_NAME
from database.db import get_session
from database.models import TopicConsidered, SourceArticle, Post


STRATEGIST_PROMPT_TEMPLATE = """You are the content writer for a Bollywood & Hollywood entertainment Instagram page. Write a post about the story below, using ONLY facts that appear in the source article text — never invent or assume anything not stated there.

Story headline: {headline}

Source article text (this is your only source of facts):
\"\"\"
{article_text}
\"\"\"
{feedback_block}
Write:
- "headline": a short, punchy on-image headline (under 10 words)
- "caption": an engaging Instagram caption (2-4 sentences) grounded in the article, in a casual entertainment-page voice
- "cta": one short call-to-action line (e.g. "Drop your thoughts below!")
- "hashtags": an array of 8-12 relevant hashtags (mix of niche-standard tags and ones specific to this story's actual people/titles/events)
- "person_name": the single real public figure this story is specifically ABOUT (not just mentioned in passing). Only return a name if the article's main subject is that individual — e.g. their announcement, their role, their statement, their project. If the story is about a group, an industry trend, box office numbers, an award ceremony as a whole, or multiple people equally, return null. Do not guess or pick the "closest" person if none is clearly the focus.
- "poster_image_description": a one-sentence description of what the poster's background image should show (describe a scene/setting; this is used for context only)
- "carousel_slides": an array of 2-3 slide captions (10-13 words each), each a complete sentence with its own subject -- do NOT drop the subject to save words (e.g. write "The film beats Force Awakens at the box office", not "Beats Force Awakens at the box office"). Each highlights one separate supporting detail from the article, stands alone without the headline slide for context, and reads naturally when spoken aloud. These become extra slides in a multi-image carousel post, alongside the main headline slide.

Respond with ONLY valid JSON, no markdown fences, no preamble, in exactly this shape:
{{
  "headline": "...",
  "caption": "...",
  "cta": "...",
  "hashtags": ["...", "..."],
  "person_name": "...",
  "poster_image_description": "...",
  "carousel_slides": ["...", "..."]
}}
"""
FEEDBACK_BLOCK_TEMPLATE = """
A previous version of this post was rejected by a human reviewer with this feedback — make sure your new version specifically addresses it:
"{feedback}"
"""
# ---------------------------------------------------------------------------
# Topic lookup
# ---------------------------------------------------------------------------

def list_candidate_topics(run_id: str | None = None) -> list[dict]:
    """Returns the selected + shortlisted topics for a run (defaults to
    the most recent run), sorted best-first — for picking an alternative
    to the auto-selected topic."""
    with get_session() as session:
        if run_id is None:
            latest = (
                session.query(TopicConsidered.run_id)
                .order_by(TopicConsidered.created_at.desc())
                .first()
            )
            if latest is None:
                return []
            run_id = latest[0]

        topics = (
            session.query(TopicConsidered)
            .filter(TopicConsidered.run_id == run_id)
            .filter(TopicConsidered.status.in_(["selected", "shortlisted"]))
            .order_by(TopicConsidered.final_score.desc())
            .all()
        )
        return [
            {
                "id": t.id,
                "headline_candidate": t.headline_candidate,
                "status": t.status,
                "final_score": t.final_score,
            }
            for t in topics
        ]


def get_topic_by_id(topic_id: str):
    """Returns one topic (any status) plus its combined source article text."""
    with get_session() as session:
        topic = session.query(TopicConsidered).filter(TopicConsidered.id == topic_id).first()
        if topic is None:
            return None, None

        source_ids = json.loads(topic.source_article_ids)
        articles = (
            session.query(SourceArticle)
            .filter(SourceArticle.id.in_(source_ids))
            .all()
        )

        topic_data = {"id": topic.id, "headline_candidate": topic.headline_candidate}
        combined_text = "\n\n---\n\n".join(
            f"[{a.source_name}] {a.title}\n{a.body_text}" for a in articles
        )
        source_names = sorted(set(a.source_name for a in articles))

    return topic_data, {"combined_text": combined_text, "source_names": source_names}


def get_selected_topic():
    """Returns the most recent topic marked 'selected' by Phase 5 (the
    original default behavior), plus its source article text."""
    with get_session() as session:
        topic = (
            session.query(TopicConsidered)
            .filter(TopicConsidered.status == "selected")
            .order_by(TopicConsidered.created_at.desc())
            .first()
        )
        if topic is None:
            return None, None
        topic_id = topic.id

    return get_topic_by_id(topic_id)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_content_with_gemini(headline: str, article_text: str, feedback: str | None = None) -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)
    feedback_block = FEEDBACK_BLOCK_TEMPLATE.format(feedback=feedback) if feedback else ""
    prompt = STRATEGIST_PROMPT_TEMPLATE.format(
        headline=headline, article_text=article_text, feedback_block=feedback_block
    )
    response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=prompt)

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").replace("json\n", "", 1)

    return json.loads(raw_text)


def create_post_for_topic(topic_id: str, feedback: str | None = None) -> dict | None:
    """Generates content for a specific topic (used both by the CLI and
    by app.py for topic-switching / rejection-feedback regeneration) and
    saves it as a new pending Post row. Returns the generated content
    dict, or None if the topic wasn't found."""
    topic, sources = get_topic_by_id(topic_id)
    if topic is None:
        return None

    content = generate_content_with_gemini(topic["headline_candidate"], sources["combined_text"], feedback)

    with get_session() as session:
        session.add(Post(
            topic_id=topic["id"],
            headline=content["headline"],
            caption=content["caption"],
            hashtags=json.dumps(content["hashtags"]),
            cta=content.get("cta"),
            source_attribution=json.dumps(sources["source_names"]),
            poster_image_description=content.get("poster_image_description"),
            person_name=content.get("person_name"),
            carousel_slides_json=json.dumps(content.get("carousel_slides", [])),
            approval_status="pending",
            publish_mode="mock",
        ))

    return content


def run_content_strategist(topic_id: str | None = None):
    """CLI-friendly entrypoint: uses the given topic_id, or falls back to
    the auto-selected topic if none is given."""
    if topic_id is None:
        topic, _ = get_selected_topic()
        if topic is None:
            print("No 'selected' topic found — run Phase 5 (topic_scout) first.")
            return
        topic_id = topic["id"]

    content = create_post_for_topic(topic_id)
    if content is None:
        print(f"No topic found with id {topic_id}.")
        return

    print(f"\nGenerated content for topic {topic_id}\n")
    print(f"Headline: {content['headline']}")
    print(f"\nCaption:\n{content['caption']}")
    print(f"\nCTA: {content.get('cta')}")
    print(f"\nHashtags: {' '.join('#' + h.lstrip('#') for h in content['hashtags'])}")
    print(f"\nPerson: {content.get('person_name')}")
    print(f"\nSuggested image: {content['poster_image_description']}\n")


if __name__ == "__main__":
    candidates = list_candidate_topics()
    if not candidates:
        print("No candidate topics found — run Phase 5 (topic_scout) first.")
    else:
        print("\nCandidate topics from the latest run:\n")
        for i, c in enumerate(candidates, start=1):
            marker = " (auto-selected)" if c["status"] == "selected" else ""
            print(f"  {i}. [{c['final_score']:.3f}] {c['headline_candidate']}{marker}")

        choice = input(f"\nPick a number (1-{len(candidates)}), or press Enter for the auto-selected one: ").strip()
        if choice == "":
            chosen_id = next(c["id"] for c in candidates if c["status"] == "selected")
        else:
            chosen_id = candidates[int(choice) - 1]["id"]

        run_content_strategist(topic_id=chosen_id)