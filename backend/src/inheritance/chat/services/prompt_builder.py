# 담당: [B] | 책임: 질문과 허용된 근거를 모델 중립 메시지로 조립한다.
# PRD: E3 / 스토리 3-3 / 태스크 3-3-4.
# 구현할 기능: RAG 안내자료, MCP 조문, OPEN API 부칙 전문을 서로 구분해 전달한다.
# 완료 기준: 각 근거의 식별자와 출처 정보가 원문 유형에 맞게 유지된다.
# 제한사항: 추가 LLM 호출·외부 법령 조회·질문 원문 영구 저장을 하지 않는다.
# 상태: PRD 태스크 미시작.
"""최종 답변 생성 입력 조립 포트. 구현 코드는 B 담당이 작성한다."""

from __future__ import annotations

from typing import Protocol

from starter_llm.contracts.models import ModelMessage
from starter_rag.contracts.models import Evidence

from inheritance.contracts.law import LawEvidence

# V1 임시 지시문(검수 전). 근거 인용 형식 [[근거ID]]는 citation_validation.py와 맞춰야 한다.
ANSWER_SYSTEM_PROMPT = (
    "아래에 주어진 근거만 사용해 답하세요. 근거에 없는 내용은 말하지 마세요.\n"
    "문장마다 사용한 근거의 ID를 [[근거ID]] 형식으로 붙이세요.\n"
    "근거가 여러 개면 [[ID1]][[ID2]]처럼 하나씩 따로 붙이고, 한 괄호에 여러 ID를 넣지 마세요.\n"
    "개인별 법률 결론이나 판정을 내리지 마세요.\n"
    # 화면은 줄바꿈만 그대로 보여 주고 마크다운은 꾸미지 않는다(frontend chat-page whitespace-pre-wrap).
    "\n[답변 형식]\n"
    "- 첫 문장에서 질문에 대한 핵심을 한두 문장으로 요약하세요.\n"
    "- 비교하거나 여러 항목을 설명할 때만, 빈 줄을 두고 '■ 제목' 줄로 문단을 나누세요.\n"
    "  예: ■ 한정승인 / ■ 상속포기 / ■ 차이점\n"
    "- 문단 안의 항목은 '- '로 시작하는 짧은 문장으로 쓰세요.\n"
    "- 짧은 질문은 문단을 나누지 말고 몇 문장으로만 답하세요.\n"
    "- **, #, 표 같은 마크다운 기호는 쓰지 마세요.\n"
    "- 어려운 법률 용어는 쉬운 말로 풀어 쓰세요."
)


class AnswerPromptBuilderPort(Protocol):
    # 질문과 RAG·법령 근거를 ModelMessage로 만들고 근거별 출처 정보를 유지한다.
    def build(
        self,
        question: str,
        rag: tuple[Evidence, ...],
        laws: tuple[LawEvidence, ...],
        previous_questions: tuple[str, ...] = (),
    ) -> tuple[ModelMessage, ...]: ...


def _rag_block(item: Evidence) -> str:
    source = item.source
    return (
        f"[[{item.evidence_id}]] {source.title} | 기관: {source.publisher} | "
        f"위치: {item.location} | 버전: {source.version} | {source.url}\n{item.text}"
    )


def _law_block(item: LawEvidence) -> str:
    return (
        f"[[{item.evidence_id}]] {item.law_title} {item.article_number} | "
        f"시행일: {item.effective_from} | {item.official_url}\n{item.article_text}"
    )


class AnswerPromptBuilder:
    # RAG 안내자료와 법령 조문·부칙을 서로 다른 구역에 넣는다. 비어 있는 구역은 넣지 않는다.
    def build(
        self,
        question: str,
        rag: tuple[Evidence, ...],
        laws: tuple[LawEvidence, ...],
        previous_questions: tuple[str, ...] = (),
    ) -> tuple[ModelMessage, ...]:
        sections: list[str] = []
        if previous_questions:
            sections.append("[이전 질문]\n" + "\n".join(f"- {q}" for q in previous_questions))
        groups = (
            ("[안내자료]", [_rag_block(item) for item in rag]),
            ("[법령 조문]", [_law_block(item) for item in laws if item.kind == "article"]),
            ("[법령 부칙]", [_law_block(item) for item in laws if item.kind == "addendum"]),
        )
        sections.extend(f"{title}\n" + "\n\n".join(blocks) for title, blocks in groups if blocks)
        sections.append(f"[질문]\n{question}")
        return (
            ModelMessage("system", ANSWER_SYSTEM_PROMPT),
            ModelMessage("user", "\n\n".join(sections)),
        )
