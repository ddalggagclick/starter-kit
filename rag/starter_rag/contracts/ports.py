# 담당: [D] | 책임: 검색·임베딩·벡터 저장의 공개 Port.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (공개 계약 지원)
# 구현할 기능: 승인 자료 검색과 적재 경계의 호출 형태를 고정한다.
# 완료 기준: Backend는 SearchPort와 공개 DTO만 사용한다.
# 제한사항: DB·pgvector 구현 타입을 공개 계약에 노출하지 않는다.
"""[D] RAG 공개 Port. 구현할 기능: 승인 자료 검색과 임베딩/적재/게시의 호출 형태 고정.
경계: backend는 SearchPort만 사용; PGVectorStore·SQLAlchemy 타입 노출 금지.
완료: FakeSearch/FakeVector와 실제 어댑터의 계약 테스트가 동일하게 통과.
"""

from __future__ import annotations

from typing import Protocol

from starter_rag.contracts.models import ChunkRecord, DocumentVersion, SearchRequest, SearchResult


class SearchPort(Protocol):
    # 검수·게시된 안내 자료만 검색하고 공식 URL·게시 버전·문서 위치를 보존해 반환한다.
    async def search(self, request: SearchRequest) -> SearchResult: ...


class EmbeddingPort(Protocol):
    async def embed_query(self, text: str) -> tuple[float, ...]: ...
    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class VectorPort(Protocol):
    async def upsert(self, chunks: tuple[ChunkRecord, ...]) -> None: ...
    async def search_dense(self, request: SearchRequest) -> SearchResult: ...
    async def get_by_id(self, chunk_id: str) -> ChunkRecord | None: ...
    async def delete_version(self, source_id: str, version: str) -> None: ...


class PublicationPort(Protocol):
    async def publish(self, source_id: str, version: str) -> DocumentVersion: ...


class IngestionPort(Protocol):
    async def ingest(self, document: DocumentVersion) -> DocumentVersion: ...
