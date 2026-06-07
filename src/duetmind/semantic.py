from __future__ import annotations

from typing import Protocol, Sequence

from duetmind.scoring import cosine_distance_from_token_sets


class TextEncoder(Protocol):
    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> Sequence[Sequence[float]]: ...


class SemanticDriftAnalyzer:
    """Computes semantic drift distance in [0,1].

    Uses sentence-transformers when available; falls back to token cosine distance.
    """

    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        encoder: TextEncoder | None = None,
        auto_load: bool = True,
    ) -> None:
        self.model_name = model_name
        self._encoder = encoder
        if self._encoder is None and auto_load:
            self._encoder = self._try_load_encoder(model_name)

    @staticmethod
    def _try_load_encoder(model_name: str) -> TextEncoder | None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:
            return None
        try:
            return SentenceTransformer(model_name)
        except Exception:
            return None

    @staticmethod
    def _vector_cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
        if len(a) != len(b) or len(a) == 0:
            return 1.0
        dot = sum(float(x) * float(y) for x, y in zip(a, b))
        norm_a = sum(float(x) * float(x) for x in a) ** 0.5
        norm_b = sum(float(y) * float(y) for y in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0
        cosine = dot / (norm_a * norm_b)
        if cosine < -1.0:
            cosine = -1.0
        if cosine > 1.0:
            cosine = 1.0
        return 1.0 - cosine

    def distance(self, a_text: str, b_text: str) -> float:
        if not a_text.strip() or not b_text.strip():
            return 1.0

        if self._encoder is not None:
            try:
                embeddings = self._encoder.encode([a_text, b_text], normalize_embeddings=True)
                return self._vector_cosine_distance(embeddings[0], embeddings[1])
            except Exception:
                pass

        return cosine_distance_from_token_sets(a_text, b_text)
