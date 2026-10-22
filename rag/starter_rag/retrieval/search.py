# 담당: [D] | 책임: 게시된 공식 안내자료 벡터 검색.
# PRD: E3 / 스토리 3-3 / 태스크 3-3-1; E6 / 스토리 6-2 / 태스크 6-2-1
# 구현할 기능: 검색 범위를 제한하고 출처·위치·점수를 SearchPort 결과로 변환한다.
# 완료 기준: 검수·게시된 자료만 검색되고 출처 URL과 원문 위치가 반환된다.
# 제한사항: 법령 원문을 벡터 검색에 저장하거나 검색하지 않는다.
"""Search adapter that turns eligible pgvector hits into public Evidence DTOs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef
from starter_rag.contracts.ports import EmbeddingPort, SearchPort
from starter_rag.storage.vector_store import PGVectorStore


@dataclass
class PGVectorSearch(SearchPort):
    vector_store: PGVectorStore
    embedding: EmbeddingPort
    allow_synthetic: bool = False

    async def search(self, request: SearchRequest) -> SearchResult:
        # SearchRequest enforces the public 1..10 range and default top_k=3.
        vector = await self.embedding.embed_query(request.query)
        hits = await self.vector_store.search_vectors(
            vector,
            top_k=request.top_k,
            allow_synthetic=self.allow_synthetic,
        )
        evidence: list[Evidence] = []
        for hit in hits:
            metadata = hit.metadata
            if metadata.get("publication_state") != "published":
                continue
            if not self.allow_synthetic and metadata.get("is_synthetic") is not False:
                continue
            source_id = metadata.get("source_id")
            title = metadata.get("source_title")
            url = metadata.get("source_url")
            publisher = metadata.get("publisher")
            version = metadata.get("version")
            location = metadata.get("location")
            if not all(isinstance(value, str) and value.strip() for value in (
                source_id, title, publisher, version, location, hit.text
            )):
                continue
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            score = 1.0 - hit.cosine_distance
            if not math.isfinite(score):
                continue
            try:
                source = SourceRef(
                    source_id=source_id,
                    title=title,
                    url=url,
                    publisher=publisher,
                    version=version,
                )
                item = Evidence(
                    evidence_id=hit.chunk_id,
                    source=source,
                    text=hit.text,
                    location=location,
                    score=score,
                )
            except ValueError:
                # Do not synthesize missing or invalid provenance.
                continue
            evidence.append(item)
        evidence.sort(key=lambda item: item.score if item.score is not None else -math.inf, reverse=True)
        return SearchResult(evidence=tuple(evidence[: request.top_k]))
