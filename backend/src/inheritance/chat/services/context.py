# 담당: [B] | 책임: 채팅 입력 길이와 이전 질문 문맥을 제한한다.
# PRD: E3 / 스토리 3-1, 3-6 / 태스크 3-1-3, 3-6-4.
# 구현할 기능: 질문은 200 Unicode 코드 포인트 이하로 받고 같은 채팅의 이전 사용자 질문을 최대 3개 사용한다.
# 완료 기준: 현재 질문·AI 답변·다른 대화·설문을 이전 질문 수에 포함하지 않는다.
# 제한사항: 추가 확인 질문을 만들지 않고 채팅 원문을 영구 저장하지 않는다.
# 상태: PRD 태스크 미시작.
"""채팅 입력 검사. 승인된 T5 정책(ChatInputPolicy)만 적용한다."""

from __future__ import annotations

from inheritance.contracts.chat import ChatInputPolicy

_POLICY = ChatInputPolicy()


# 현재 질문과 같은 채팅의 이전 사용자 질문(0~3개)을 검사한다.
# 넘치면 자르거나 요약하지 않고 ValueError로 거부한다. 이전 질문에는 AI 답변을 넣지 않는다.
def validate_chat_input(question: str, previous_questions: tuple[str, ...] = ()) -> None:
    _POLICY.validate_question(question)
    _POLICY.validate_history_count(len(previous_questions))
    for previous in previous_questions:
        _POLICY.validate_question(previous)
