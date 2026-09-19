# Nichely — AI-Powered Instagram Content Automation

Nichely is an autonomous, agentic AI pipeline that researches trending entertainment news (Bollywood & Hollywood), decides what's worth posting, generates ready-to-publish content, and publishes it live to Instagram — with a human approval step in between.

## What it does

1. **Researches** the latest entertainment news via NewsAPI, scoring each source for reliability
2. **Deduplicates** similar stories using sentence embeddings + cosine similarity
3. **Ranks candidate topics** (Topic Scout Agent) on recency, relevance, reliability, novelty, and audience appeal — combining rule-based scoring with Gemini's judgment
4. **Generates content** (Content Strategist Agent) — a headline, caption, hashtags, and CTA via Google Gemini, strictly grounded in the real article text to avoid hallucination
5. **Generates a poster image** with the headline overlaid, using Stable Diffusion for the background
6. **Supports carousel/slideshow posts** — multiple slides generated and published as one Instagram carousel
7. **Human approval screen** (Streamlit) — approve, reject with feedback (triggers regeneration), or pick an alternate shortlisted topic
8. **Publishes live to Instagram** via the official Graph API (two-step container → publish flow), or simulates it in mock mode for safe testing
9. **Tracks performance** and feeds approve/reject outcomes back into adjusting the scoring weights over time

## Tech Stack

- **Frontend/Dashboard:** Streamlit
- **LLM:** Google Gemini (content generation + topic judgment)
- **Embeddings:** Sentence-Transformers (deduplication + relevance)
- **Image generation:** Stable Diffusion XL (via Hugging Face Inference API)
- **Image hosting:** Cloudinary
- **Publishing:** Instagram Graph API (Instagram Login flow)
- **Database:** SQLite + SQLAlchemy
- **News source:** NewsAPI.org

## Project Structure

nichely/
├── agents/ — Topic Scout & Content Strategist AI agents
├── services/ — Research, dedup, poster generation, Instagram publishing, analytics
├── database/ — SQLAlchemy models and DB setup
├── tests/ — Phase-by-phase test scripts
├── utils/ — Helper utilities
├── app.py — Streamlit dashboard (main entry point)
├── pipeline.py — Orchestrates the full pipeline end-to-end
├── config.py — Niche/config settings
└── requirements.txt

## Setup & Installation

1. **Create a virtual environment**

   python -m venv venv

   venv\Scripts\activate      (Windows)

   source venv/bin/activate   (Mac/Linux)

2. **Install dependencies**

   pip install -r requirements.txt

3. **Configure environment variables**

   Copy `.env.example` to `.env` and fill in your own keys:
   - `GEMINI_API_KEY` — Google Gemini API key
   - `NEWS_API_KEY` — NewsAPI.org key
   - `CLOUDINARY_URL` — Cloudinary connection string
   - `IG_APP_ID`, `IG_APP_SECRET`, `IG_ACCESS_TOKEN`, `IG_USER_ID` — from a Meta Developer App with Instagram Login configured
   - `PUBLISH_MODE` — `mock` (safe testing, no real posting) or `live` (publishes for real)

4. **Run the app**

   streamlit run app.py

   Opens at localhost:8501

## How to Use

Click **"Run one pipeline cycle now"** in the sidebar to fetch news, rank topics, and generate content for the top pick. Review the generated poster, caption, and hashtags, then:
- **Approve & Publish** — finalizes the post (live or mock, depending on `PUBLISH_MODE`)
- **Reject** with feedback — regenerates the content addressing what was wrong
- Pick a different **shortlisted topic** instead of the auto-selected one

Once approved, click **Fetch analytics** to pull performance data, which feeds into future topic scoring.



