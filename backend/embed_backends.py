# file: backend/embed_backends.py
from __future__ import annotations

import os
from typing import List

import numpy as np

try:
    from fastembed import TextEmbedding as _FastEmbed
except Exception:
    _FastEmbed = None


class Embedder:
    """Swappable embedding interface; keeps retrieval code backend-agnostic."""
    def embed(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


class FastEmbedder(Embedder):
    """Offline CPU-friendly embeddings via fastembed."""
    def __init__(self, model_name: str | None = None):
        if _FastEmbed is None:
            raise RuntimeError(
                "fastembed is not installed. Ensure it's in requirements and installed."
            )
        self.model_name = model_name or os.getenv(
            "EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5"
        )
        self.model = _FastEmbed(model_name=self.model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        vecs = list(self.model.embed(texts))  # generator -> list
        return np.asarray(vecs, dtype=np.float32)


class GeminiEmbedder(Embedder):
    """Placeholder if you later switch to Gemini embeddings."""
    def __init__(self):
        raise NotImplementedError(
            "Gemini embeddings backend not implemented in this starter. "
            "Use FastEmbedder now; we can add Gemini later."
        )

    def embed(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError


def build_embedder() -> Embedder:
    backend = os.getenv("EMBEDDINGS_BACKEND", "fastembed").lower()
    if backend == "fastembed":
        return FastEmbedder()
    if backend == "gemini":
        return GeminiEmbedder()
    raise ValueError(f"Unknown EMBEDDINGS_BACKEND: {backend}")
