# 담당: [B] | 책임: 실제 근거 ID를 검증하고 화면용 AnswerReference를 만든다.
# PRD: E3 / 스토리 3-4 / 태스크 3-4-2; E6 / 스토리 6-2 / 태스크 6-2-2.
# 구현할 기능: RAG·법령 결과에 있는 ID만 인용으로 허용하고 공식 URL·위치·버전을 연결한다.
# 완료 기준: 임의 ID·URL을 거부하고 근거마다 개별 출처를 반환한다.
# 제한사항: 별도 LLM을 호출하지 않는다. 출처가 있다는 이유만으로 원문 정확성을 보증하지 않는다.
# 상태: PRD 태스크 미시작.
"""출처 검사 내부 Port. HTTP SSE/외부 서비스 호출 책임이 없다."""

from __future__ import annotations

from typing import Protocol

from starter_rag.contracts.models import Evidence

from inheritance.contracts.chat import AnswerReference
from inheritance.contracts.law import LawEvidence


class CitationValidatorPort(Protocol):
    # cited_ids를 검색 결과와 대조해 실제 근거의 공식 URL·위치·버전만 반환한다.
    def validate_and_resolve(
        self, cited_ids: tuple[str, ...], rag: tuple[Evidence, ...], laws: tuple[LawEvidence, ...]
    ) -> tuple[AnswerReference, ...]: ...
