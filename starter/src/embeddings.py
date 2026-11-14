"""Real local embedding provider using Sentence Transformers (multilingual MiniLM)."""
import os
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Sentence-Transformers adapter for multilingual semantic embeddings (no mock fallback)."""

    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model_name: str | None = None, batch_size: int = 32) -> None:
        resolved_model = (
            model_name
            or os.getenv("EMBEDDING_MODEL")
            or self.DEFAULT_MODEL
        ).strip()
        if not resolved_model:
            resolved_model = self.DEFAULT_MODEL

        # Use local HF cache if present
        local_hf_cache = Path(
            r"C:\Users\xuand\.gemini\antigravity\brain\bea5a12c-cc45-4968-b2c3-e992bc882f30\scratch\hf_cache"
        )
        if "HF_HOME" not in os.environ and local_hf_cache.exists():
            os.environ["HF_HOME"] = str(local_hf_cache)
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

        from sentence_transformers import SentenceTransformer

        self.model_name = resolved_model
        self.batch_size = batch_size

        try:
            # Try loading from local cache first to avoid unnecessary network calls
            self._model = SentenceTransformer(self.model_name, local_files_only=True)
        except Exception:
            # Fall back to downloading from Hugging Face Hub if not yet cached locally
            self._model = SentenceTransformer(self.model_name)

        if hasattr(self._model, "get_embedding_dimension"):
            dim = self._model.get_embedding_dimension()
        else:
            dim = self._model.get_sentence_embedding_dimension()
        if not dim or dim <= 0:
            raise RuntimeError(f"Invalid embedding dimension returned by model {self.model_name}: {dim}")
        self.dimensions: int = int(dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [t if (t and t.strip()) else " " for t in texts]
        embeddings = self._model.encode(
            cleaned,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        result = embeddings.tolist()
        if len(result) != len(texts):
            raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(result)}")
        return result

    def embed_query(self, question: str) -> list[float]:
        if not question or not question.strip():
            raise ValueError("Query question must not be empty")
        embedding = self._model.encode(
            [question.strip()],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        vec = embedding[0].tolist()
        if len(vec) != self.dimensions:
            raise RuntimeError(f"Query vector dimension mismatch: {len(vec)} != {self.dimensions}")
        return vec
