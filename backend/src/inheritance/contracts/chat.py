# 담당: [B] | 책임: 채팅 최종 답변 및 검증된 개별 공식 출처 계약
# 구현할 기능: AnswerReference 목록, RAG/법령 근거 연결, S6/S7/S9 및 T5 입력 제한
# 코드 경계: SSE wire와 HTTP DTO는 API 담당자, 검증 전 원문은 화면에 공개하지 않는다.
# 완료 기준: 출처 없는 answered 거부, 실패 결과 본문 거부, Unicode 200/과거 3/추가 질문 0 테스트 통과.
"""내부 DTO. 응답은 출처 문자열 ID가 아니라 공식 URL·위치를 가진 근거 목록으로 연결."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MAX_QUESTION_CODEPOINTS = 200
MAX_PREVIOUS_MESSAGES = 3
MAX_CLARIFICATION_QUESTIONS = 0


@dataclass(frozen=True)
class ChatInputPolicy:
    max_question_codepoints: int = MAX_QUESTION_CODEPOINTS
    max_previous_messages: int = MAX_PREVIOUS_MESSAGES
    max_clarification_questions: int = MAX_CLARIFICATION_QUESTIONS

    def __post_init__(self) -> None:
        if (
            self.max_question_codepoints,
            self.max_previous_messages,
            self.max_clarification_questions,
        ) != (200, 3, 0):
            raise ValueError("approved T5 policy cannot be overridden")

    def validate_question(self, question: str) -> None:
        if not question.strip() or len(question) > 200:
            raise ValueError("question must contain 1..200 Unicode code points")

    def validate_history_count(self, count: int) -> None:
        if not 0 <= count <= 3:
            raise ValueError("previous message count must be 0..3")


ReferenceKind = Literal["procedure", "law_article", "law_addendum"]


@dataclass(frozen=True)
class AnswerReference:
    evidence_id: str
    kind: ReferenceKind
    title: str
    official_url: str
    location: str
    version: str

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.title, self.official_url, self.location, self.version)):
            raise ValueError("answer reference requires source identity/title/url/location/version")
        if self.kind not in (
            "procedure",
            "law_article",
            "law_addendum",
        ) or not self.official_url.startswith("https://"):
            raise ValueError("answer references must be official HTTPS sources")


AnswerStatus = Literal["answered", "partial", "technical_error", "abstained", "limited"]


@dataclass(frozen=True)
class AnswerOutcome:
    status: AnswerStatus
    answer_text: str | None
    references: tuple[AnswerReference, ...]
    request_id: str

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request id required")
        if self.status in ("answered", "partial") and (not self.answer_text or not self.references):
            raise ValueError("grounded answer requires text and actual verified references")
        if self.status in ("technical_error", "abstained", "limited") and (
            self.answer_text or self.references
        ):
            raise ValueError("failure/abstention cannot expose answer or verified citations")
