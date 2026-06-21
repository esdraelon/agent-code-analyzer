from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from .config import get_config

DEFAULT_EMBEDDING_MODEL = get_config().vector.embedding_model


class EmbeddingProvider(Protocol):
    @property
    def vector_size(self) -> int:
        ...

    def embed_document(self, text: str) -> list[float]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass
class SentenceTransformerEmbeddingProvider:
    """Real embedding backend for code and text retrieval."""

    model_name: str = DEFAULT_EMBEDDING_MODEL
    _model: Any | None = field(default=None, init=False, repr=False)
    _vector_size: int | None = field(default=None, init=False, repr=False)

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - install-time guard
            raise RuntimeError(
                "sentence-transformers is required for real embeddings. Install dependencies with `uv sync`."
            ) from exc

        self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, text: str, *, is_query: bool) -> list[float]:
        model = self._load_model()
        prefix = "query: " if is_query else "passage: "
        vector = model.encode(
            [prefix + text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        values = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        if self._vector_size is None:
            self._vector_size = len(values)
        return [float(value) for value in values]

    @property
    def vector_size(self) -> int:
        if self._vector_size is None:
            self._vector_size = len(self.embed_document("embedding dimension probe"))
        return self._vector_size

    def embed_document(self, text: str) -> list[float]:
        return self._encode(text, is_query=False)

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text, is_query=True)


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    return SentenceTransformerEmbeddingProvider()
