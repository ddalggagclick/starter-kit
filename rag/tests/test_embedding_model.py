"""EmbeddingGemma 어댑터의 입력 형식과 출력 검증을 확인한다."""

from __future__ import annotations

import asyncio
import unittest

from starter_rag.embedding.model import (
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_REVISION,
    EmbeddingGenerationError,
    EmbeddingGemma,
    EmbeddingInitializationError,
    EmbeddingOutputError,
)


class _FakeEncoder:
    def __init__(self, output: object = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def encode(self, texts, *, prompt: str, **kwargs):
        self.calls.append((tuple(texts), prompt))
        if self.error is not None:
            raise self.error
        return self.output


def _vectors(count: int) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(0.25 for _ in range(768)) for _ in range(count))


class EmbeddingGemmaUnitTests(unittest.TestCase):
    def test_모델_ID와_revision을_고정한다(self) -> None:
        observed: list[tuple[str, str]] = []

        def model_loader(model_id: str, revision: str):
            observed.append((model_id, revision))
            return _FakeEncoder(_vectors(1))

        embedding = EmbeddingGemma(model_loader=model_loader)
        asyncio.run(embedding.embed_query("질문"))

        self.assertEqual(observed, [(EMBEDDING_MODEL_ID, EMBEDDING_MODEL_REVISION)])
        self.assertEqual(EMBEDDING_MODEL_ID, "google/embeddinggemma-2")
        self.assertEqual(
            EMBEDDING_MODEL_REVISION,
            "914f7f89142e33e77833254d9c9b90c3cef7303b",
        )

    def test_질의와_문서는_검색용_프롬프트를_구분한다(self) -> None:
        encoder = _FakeEncoder(_vectors(1))
        embedding = EmbeddingGemma(model_loader=lambda *_: encoder)

        query_vector = asyncio.run(embedding.embed_query("상속 금융 조회"))
        document_vectors = asyncio.run(embedding.embed_documents(("금융 조회 안내",)))

        self.assertEqual(len(query_vector), 768)
        self.assertEqual(len(document_vectors[0]), 768)
        self.assertEqual(
            encoder.calls,
            [
                (("상속 금융 조회",), "task: search result | query: "),
                (("금융 조회 안내",), "title: none | text: "),
            ],
        )

    def test_768가_아닌_벡터를_거부한다(self) -> None:
        encoder = _FakeEncoder((tuple(0.1 for _ in range(767)),))
        embedding = EmbeddingGemma(model_loader=lambda *_: encoder)

        with self.assertRaises(EmbeddingOutputError):
            asyncio.run(embedding.embed_query("질문"))

    def test_빈_벡터와_nan_infinity를_거부한다(self) -> None:
        invalid_outputs = (
            ((),),
            ((float("nan"),) + tuple(0.0 for _ in range(767)),),
            ((float("inf"),) + tuple(0.0 for _ in range(767)),),
        )

        for output in invalid_outputs:
            with self.subTest(first_value=output[0][0] if output[0] else "empty"):
                embedding = EmbeddingGemma(model_loader=lambda *_: _FakeEncoder(output))
                with self.assertRaises(EmbeddingOutputError):
                    asyncio.run(embedding.embed_query("질문"))

    def test_초기화_오류와_임베딩_오류를_구분한다(self) -> None:
        initialization_failure = EmbeddingGemma(
            model_loader=lambda *_: (_ for _ in ()).throw(RuntimeError("load"))
        )
        with self.assertRaises(EmbeddingInitializationError):
            asyncio.run(initialization_failure.embed_query("질문"))

        encoder = _FakeEncoder(error=RuntimeError("encode"))
        embedding_failure = EmbeddingGemma(model_loader=lambda *_: encoder)
        with self.assertRaises(EmbeddingGenerationError):
            asyncio.run(embedding_failure.embed_query("질문"))


if __name__ == "__main__":
    unittest.main()
