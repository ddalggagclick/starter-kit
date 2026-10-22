# 담당: [D] | 책임: 공식 안내자료의 문서·버전·청크 메타데이터.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-3 (저장 모델 지원)
# 구현할 기능: 문서 버전과 게시 상태를 벡터 자료에 연결한다.
# 완료 기준: 검색 자료에서 문서 버전과 원문 위치를 찾을 수 있다.
# 제한사항: 승인된 로컬 rag_test.chunks 외 스키마 변경은 하지 않는다.
"""Storage constants and validation helpers for the approved local RAG table."""

from __future__ import annotations

from starter_rag.contracts.models import PublicationState

DATABASE_NAME = "starter_rag_integration"
SCHEMA_NAME = "rag_test"
TABLE_NAME = "chunks"
VECTOR_DIMENSION = 768
DEFAULT_COLLECTION_ID = "published-guides"
PUBLICATION_STATES: tuple[PublicationState, ...] = (
    "staging",
    "indexed",
    "published",
    "failed",
    "retired",
)


def validate_publication_state(state: str) -> PublicationState:
    if state not in PUBLICATION_STATES:
        raise ValueError(f"unsupported publication state: {state}")
    return state  # type: ignore[return-value]
