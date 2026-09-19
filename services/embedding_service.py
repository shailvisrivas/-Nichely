"""
Embedding service — Phase 4.

Wraps a local sentence-transformers model so the rest of the codebase
never has to think about the model directly. Embeddings are stored in
the database as JSON-serialized float lists (see database/models.py) —
no vector database needed at this project's scale (see spec §7).

The model downloads once (a few hundred MB) the first time this runs,
then is cached locally by sentence-transformers/huggingface_hub —
expect the first run to take longer than later ones.
"""

import json
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Loads the model once per process and reuses it (loading is slow,
    embedding individual texts with an already-loaded model is fast)."""
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """Returns a plain Python list of floats for one piece of text."""
    model = get_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.tolist()


def embedding_to_json(embedding: list[float]) -> str:
    return json.dumps(embedding)


def embedding_from_json(embedding_json: str) -> np.ndarray:
    return np.array(json.loads(embedding_json), dtype=np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Both vectors are already normalized by embed_text(), so cosine
    similarity is just the dot product — cheap to compute at this scale."""
    return float(np.dot(vec_a, vec_b))
