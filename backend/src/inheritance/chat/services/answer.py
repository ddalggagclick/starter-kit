# 담당: [B] | 책임: 근거 검색과 최종 답변 생성을 조립한다.
# PRD: E3 / 스토리 3-2, 3-3, 3-4, 3-5 / 태스크 3-2-3, 3-3-2, 3-3-3, 3-4-1, 3-5-3.
# 구현할 기능: SearchPort·LawPort 결과를 소비하고 근거가 있을 때 최종 답변을 한 번 생성한다.
# 완료 기준: 검증된 답변만 반환하고 S6·S7·S9를 구분한다.
# 제한사항: 프롬프트와 인용 검증은 전담 모듈에 위임한다. 근거가 없으면 최종 답변을 생성하지 않는다.
# 상태: PRD 태스크 미시작. Fake 계약 검증은 테스트 영역의 책임이다.
"""채팅 서비스 연결점. 실제 알고리즘과 API 엔드포인트는 담당자 구현 PR에서 작성."""

from __future__ import annotations

from typing import Protocol

from inheritance.contracts.chat import AnswerOutcome


class ChatAnswerService(Protocol):
    # 성공·부분 답변에만 검증된 출처를 담고, 오류·유보 결과에는 본문을 담지 않는다.
    async def answer(self, question: str, request_id: str) -> AnswerOutcome: ...


# 주의: QuestionRouterPort.classify()가 Gemini ModelPort.generate() 한 번 호출한다.
# 최종 답변 작성은 ModelPort.stream() 한 번. 재심사 LLM/자동 Ollama 전환 금지.
# 경로 분류는 근거가 아니다. 검증된 출처만 AnswerOutcome.references로 내보낸다.
