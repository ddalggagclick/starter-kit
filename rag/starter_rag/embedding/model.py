# 담당: [D] | 책임: EmbeddingGemma 기반 문서·질의 임베딩.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-2
# 구현할 기능: 입력 유형에 맞는 임베딩과 768차원 검증을 제공한다.
# 완료 기준: 저장·검색 벡터가 같은 모델 설정과 차원을 사용한다.
# 제한사항: 모델 revision을 기록하고 카카오·도메인 판단을 하지 않는다.
"""EmbeddingGemma 2 model adapter implementing the public EmbeddingPort."""

from __future__ import annotations

import asyncio
import math
import os
import threading
from collections.abc import Callable, Sequence
from typing import Any

from starter_rag.contracts.ports import EmbeddingPort

EMBEDDING_MODEL_ID = "google/embeddinggemma-2"
EMBEDDING_MODEL_REVISION = "914f7f89142e33e77833254d9c9b90c3cef7303b"
EMBEDDING_DIMENSION = 768
QUERY_PROMPT = "task: search result | query: "
DOCUMENT_PROMPT = "title: none | text: "
TEXT_ONLY_ENV = "RAG_EMBEDDING_TEXT_ONLY"


class EmbeddingError(RuntimeError):
    """Base error for model-backed embedding failures."""


class EmbeddingInitializationError(EmbeddingError):
    """The configured model could not be loaded."""


class EmbeddingGenerationError(EmbeddingError):
    """The loaded model failed while encoding input text."""


class EmbeddingOutputError(EmbeddingError, ValueError):
    """The model returned an invalid vector or an unexpected dimension."""


ModelLoader = Callable[[str, str], Any]


def _load_sentence_transformer(model_id: str, revision: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - packaging failure depends on environment
        raise RuntimeError("sentence-transformers is not installed") from exc

    kwargs: dict[str, Any] = {
        "revision": revision,
        "local_files_only": True,
        "trust_remote_code": False,
    }
    if os.getenv(TEXT_ONLY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        kwargs["config_kwargs"] = {"vision_config": None, "audio_config": None}
    return SentenceTransformer(model_id, **kwargs)


def _as_vector_rows(output: object) -> list[list[float]]:
    if hasattr(output, "tolist"):
        output = output.tolist()  # numpy/torch outputs
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
        raise EmbeddingOutputError("embedding output must be a matrix")
    try:
        rows = [list(row) for row in output]  # type: ignore[arg-type]
    except TypeError as exc:
        raise EmbeddingOutputError("embedding output must be a matrix") from exc
    vectors: list[list[float]] = []
    for row in rows:
        if not row:
            raise EmbeddingOutputError("embedding vector must not be empty")
        try:
            vector = [float(value) for value in row]
        except (TypeError, ValueError, OverflowError) as exc:
            raise EmbeddingOutputError("embedding vector must contain finite numbers") from exc
        if len(vector) != EMBEDDING_DIMENSION:
            raise EmbeddingOutputError(
                f"expected {EMBEDDING_DIMENSION}-dimension vector; got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingOutputError("embedding vector contains NaN or Infinity")
        vectors.append(vector)
    return vectors


class EmbeddingGemma(EmbeddingPort):
    """Lazy, offline-capable adapter pinned to an approved model revision."""

    model_id = EMBEDDING_MODEL_ID
    revision = EMBEDDING_MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(self, *, model_loader: ModelLoader | None = None) -> None:
        self._model_loader = model_loader or _load_sentence_transformer
        self._encoder: Any | None = None
        self._encoder_lock = threading.Lock()

    def _get_encoder(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        with self._encoder_lock:
            if self._encoder is not None:
                return self._encoder
            try:
                self._encoder = self._model_loader(self.model_id, self.revision)
            except Exception as exc:
                raise EmbeddingInitializationError(
                    f"failed to initialize {self.model_id}@{self.revision}"
                ) from exc
        return self._encoder

    def _encode(self, texts: tuple[str, ...], prompt: str) -> tuple[tuple[float, ...], ...]:
        encoder = self._get_encoder()
        try:
            output = encoder.encode(
                list(texts),
                prompt=prompt,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingGenerationError("EmbeddingGemma encoding failed") from exc
        vectors = _as_vector_rows(output)
        if len(vectors) != len(texts):
            raise EmbeddingOutputError(f"expected {len(texts)} vectors; got {len(vectors)}")
        return tuple(tuple(vector) for vector in vectors)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("query text must not be empty")
        vectors = await asyncio.to_thread(self._encode, (text,), QUERY_PROMPT)
        return vectors[0]

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        if any(not text.strip() for text in texts):
            raise ValueError("document text must not be empty")
        return await asyncio.to_thread(self._encode, texts, DOCUMENT_PROMPT)
