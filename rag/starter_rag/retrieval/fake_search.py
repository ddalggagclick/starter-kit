# 담당: [D] | 책임: RAG 품질 검증 이전 V1의 결정적 모의 근거 제공.
# PRD: 6-1-5 (SearchPort 모의 근거 연결)
# 제한사항: 실제 공식 자료·검색 품질을 검증하거나 외부 서비스에 연결하지 않는다.
"""RAG 검색 품질 검증 전 화면 흐름을 위한 합성 근거 fixture."""

from typing import Literal

from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef
from starter_rag.contracts.ports import SearchPort

SearchScenario = Literal["evidence"]


def make_fixed_evidence() -> Evidence:
    """실제 출처로 오인되지 않는 고정 합성 Evidence를 만든다."""
    source = SourceRef(
        source_id="synthetic-test-source:inheritance-guide-v1",
        title="[합성 시험 자료] 상속 안내 시나리오",
        url="https://example.invalid/synthetic-test/inheritance-guide-v1",
        publisher="모의 기관 (합성 시험 자료)",
        version="synthetic-v1",
    )
    return Evidence(
        evidence_id="synthetic-test-evidence:inheritance-guide-v1:chunk-001",
        source=source,
        text="이 자료는 SearchPort 동작 검증을 위한 합성 테스트 자료이며 실제 법률 안내가 아니다.",
        location="합성 문서 위치: 1쪽, '상속 절차 안내' 절",
    )


class FakeSearchPort(SearchPort):
    def __init__(self, *, scenario: SearchScenario) -> None:
        if scenario != "evidence":
            raise ValueError("scenario must be 'evidence'")
        self._scenario = scenario

    async def search(self, request: SearchRequest) -> SearchResult:
        evidence = (make_fixed_evidence(),)
        return SearchResult(evidence=evidence[: request.top_k])
