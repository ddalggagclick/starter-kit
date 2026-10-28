# 담당: [B] | 책임: 실제 근거 ID를 검증하고 화면용 AnswerReference를 만든다.
# PRD: E3 / 스토리 3-4 / 태스크 3-4-2; E6 / 스토리 6-2 / 태스크 6-2-2.
# 구현할 기능: RAG·법령 결과에 있는 ID만 인용으로 허용하고 공식 URL·위치·버전을 연결한다.
# 완료 기준: 임의 ID·URL을 거부하고 근거마다 개별 출처를 반환한다.
# 제한사항: 별도 LLM을 호출하지 않는다. 출처가 있다는 이유만으로 원문 정확성을 보증하지 않는다.
# 상태: PRD 태스크 미시작.
"""출처 검사 내부 Port. HTTP SSE/외부 서비스 호출 책임이 없다."""

from __future__ import annotations

import re
from typing import Protocol

from starter_rag.contracts.models import Evidence

from inheritance.contracts.chat import AnswerReference
from inheritance.contracts.law import LawEvidence

# V1 임시 인용 형식 [[근거ID]] (prompt_builder.ANSWER_SYSTEM_PROMPT와 같은 형식).
# 모델이 [[ID1, ID2]]처럼 한 괄호에 묶어 쓰는 경우도 있어, 괄호 안을 쉼표·공백으로 나눠 읽는다.
_CITATION = re.compile(r"\[\[([^\[\]]*)\]\]")
_ID_SEPARATOR = re.compile(r"[,\s]+")


class CitationMismatch(Exception):
    pass


class CitationValidatorPort(Protocol):
    # cited_ids를 검색 결과와 대조해 실제 근거의 공식 URL·위치·버전만 반환한다.
    def validate_and_resolve(
        self, cited_ids: tuple[str, ...], rag: tuple[Evidence, ...], laws: tuple[LawEvidence, ...]
    ) -> tuple[AnswerReference, ...]: ...


def _group_ids(group: str) -> list[str]:
    return [part for part in _ID_SEPARATOR.split(group) if part]


# 답변 본문에서 인용 ID를 처음 나온 순서대로 한 번씩만 꺼낸다. 묶음 인용은 안의 ID를 하나씩 센다.
def extract_cited_ids(text: str) -> tuple[str, ...]:
    ids = (cited for group in _CITATION.findall(text) for cited in _group_ids(group))
    return tuple(dict.fromkeys(ids))


# 화면용 본문: [[근거ID]]를 처음 나온 순서의 번호 [n]으로, 묶음 [[ID1, ID2]]는 [1][2]로 바꾼다.
# [n]은 출처 목록의 n번째와 같다. 검증을 통과한 본문에만 쓴다.
# 바꾼 뒤에도 [[ 또는 ]]가 남으면(빈 괄호·짝이 안 맞는 괄호) 내부 표시가 새지 않게 CitationMismatch.
def number_citations(text: str) -> str:
    numbers = {cited: index for index, cited in enumerate(extract_cited_ids(text), start=1)}

    def replace(match: re.Match[str]) -> str:
        ids = _group_ids(match.group(1))
        return "".join(f"[{numbers[cited]}]" for cited in ids) if ids else match.group(0)

    shown = _CITATION.sub(replace, text)
    if "[[" in shown or "]]" in shown:
        raise CitationMismatch
    return shown


def _from_rag(item: Evidence) -> AnswerReference:
    source = item.source
    return AnswerReference(
        evidence_id=item.evidence_id,
        kind="procedure",
        title=source.title,
        official_url=source.url,
        location=item.location,
        version=source.version,
    )


def _from_law(item: LawEvidence) -> AnswerReference:
    return AnswerReference(
        evidence_id=item.evidence_id,
        kind="law_article" if item.kind == "article" else "law_addendum",
        title=item.law_title,
        official_url=item.official_url,
        location=item.article_number,
        version=item.effective_from,
    )


class CitationValidator:
    # 규칙으로만 대조한다. 인용이 없거나 검색되지 않은 ID가 하나라도 있으면 CitationMismatch(S7).
    def validate_and_resolve(
        self, cited_ids: tuple[str, ...], rag: tuple[Evidence, ...], laws: tuple[LawEvidence, ...]
    ) -> tuple[AnswerReference, ...]:
        # 인용된 근거만 출처로 바꾼다. 인용하지 않은 근거의 형식 문제로 답변 전체가 깨지지 않게 한다.
        known: dict[str, Evidence | LawEvidence] = {item.evidence_id: item for item in rag}
        known.update({item.evidence_id: item for item in laws})
        if not cited_ids or any(cited not in known for cited in cited_ids):
            raise CitationMismatch
        try:
            return tuple(_reference(known[cited]) for cited in cited_ids)
        except ValueError:
            # 인용된 출처가 계약(제목·위치·버전·HTTPS)을 못 채우면 검증 실패로 본다(S7).
            raise CitationMismatch from None


def _reference(item: Evidence | LawEvidence) -> AnswerReference:
    return _from_law(item) if isinstance(item, LawEvidence) else _from_rag(item)
