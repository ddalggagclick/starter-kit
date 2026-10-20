# 담당: [D] | 책임: 공식 안내자료의 검색 DTO와 출처 정보.
# PRD: E6 / 스토리 6-2 / 태스크 6-2-1 (검색 계약 지원)
# 구현할 기능: 문서 버전, 청크, 출처, 검색 결과 자료형을 고정한다.
# 완료 기준: 결과에 공식 URL, 문서 위치, 게시 버전이 포함된다.
# 제한사항: 법령 원문 조회 자료형과 검색 자료형을 분리한다.
"""[D] 공식 안내자료 검색 계약. 구현할 기능: 문서 버전·청크·출처·검색 결과 타입 고정.
입출력: SearchRequest→SearchResult(Evidence 목록); 법령 원문 조회 타입은 별개.
완료: 출처 URL·문서 위치·게시 버전 없는 Evidence는 생성 불가.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PublicationState = Literal["staging", "indexed", "published", "failed", "retired"]


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    title: str
    url: str | None
    publisher: str
    version: str

    def __post_init__(self):
        if not all((self.source_id, self.title, self.publisher, self.version)):
            raise ValueError("source requires identity, publisher, and version")
        if self.url is not None and not self.url.startswith("https://"):
            raise ValueError("official source must use https")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source: SourceRef
    text: str
    location: str
    score: float | None = None

    def __post_init__(self):
        if not self.evidence_id or not self.text or not self.location:
            raise ValueError("evidence requires text and location")
        if self.source.url is None:
            raise ValueError("evidence requires an official HTTPS URL")


@dataclass(frozen=True)
class SearchRequest:
    query: str
    top_k: int = 3  # T4 확정: 기본 3건, 상한 10건

    def __post_init__(self):
        if not self.query.strip() or not 1 <= self.top_k <= 10:
            raise ValueError("search top_k must be within 1..10")


@dataclass(frozen=True)
class SearchResult:
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class DocumentVersion:
    source: SourceRef
    content_sha256: str
    state: PublicationState
    chunk_count: int

    def __post_init__(self):
        if not self.content_sha256 or self.chunk_count < 0:
            raise ValueError("document version requires content hash and nonnegative chunk count")
        if self.state == "published" and self.source.url is None:
            raise ValueError("published document requires an official HTTPS URL")
        if self.state == "published" and self.chunk_count == 0:
            raise ValueError("empty document version cannot be published")


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    source_id: str
    version: str
    text: str
    location: str
