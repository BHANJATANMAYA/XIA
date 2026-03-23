"""
memory/embedder.py — Local Embedding Generator

Converts text into vector embeddings using a local model.
Embeddings are what allow xia to find semantically similar memories —
"what's my name" will match "user told me their name is Aryan" even
though no keywords overlap.

Model: all-MiniLM-L6-v2
  - ~90MB download, runs fully locally
  - 384-dimensional embeddings
  - Fast enough for real-time use on CPU
  - Stored on SSD, never re-downloaded

Usage:
    embedder = Embedder()
    vector = embedder.embed("user prefers Python over JavaScript")
    vectors = embedder.embed_batch(["text1", "text2", "text3"])
"""

import os
from typing import List, Optional

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS

log = get_logger(__name__)


class Embedder:
    """
    Wraps sentence-transformers to generate local embeddings.
    Lazy-loads the model on first use to keep startup fast.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or cfg.memory.embedding_model
        self._model = None  # Lazy loaded

    def embed(self, text: str) -> List[float]:
        """
        Embed a single string into a vector.
        Returns a list of floats (384 dimensions for MiniLM).
        """
        if not text or not text.strip():
            return self._zero_vector()

        model = self._get_model()
        if model is None:
            return self._zero_vector()

        try:
            vector = model.encode(text.strip(), normalize_embeddings=True)
            return vector.tolist()
        except Exception as e:
            log.error("Embedding failed: %s", e)
            return self._zero_vector()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple strings efficiently in one batch.
        Much faster than calling embed() in a loop.
        """
        if not texts:
            return []

        model = self._get_model()
        if model is None:
            return [self._zero_vector() for _ in texts]

        try:
            clean = [t.strip() if t and t.strip() else " " for t in texts]
            vectors = model.encode(clean, normalize_embeddings=True, show_progress_bar=False)
            return [v.tolist() for v in vectors]
        except Exception as e:
            log.error("Batch embedding failed: %s", e)
            return [self._zero_vector() for _ in texts]

    def is_available(self) -> bool:
        """Check if the embedding model is loaded and working."""
        return self._get_model() is not None

    # ── Internal ───────────────────────────────────────────────────────────

    def _get_model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer

            # Tell sentence-transformers to cache models on the SSD
            cache_dir = str(PATHS.models_dir / "embeddings_cache")
            os.makedirs(cache_dir, exist_ok=True)

            log.info("Loading embedding model: %s (first load may take a moment)", self.model_name)
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=cache_dir,
            )
            log.info("Embedding model loaded successfully")
            return self._model

        except ImportError:
            log.error(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            return None
        except Exception as e:
            log.error("Failed to load embedding model '%s': %s", self.model_name, e)
            return None

    def _zero_vector(self) -> List[float]:
        """Return a zero vector as fallback when embedding fails."""
        return [0.0] * 384
