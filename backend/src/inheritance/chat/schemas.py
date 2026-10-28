# 담당: [B] | 책임: [B] AI 질문·답변·출처 API 스키마 자리
# 구현할 기능: S1~S9 화면 상태와 API 상태 연결; API 담당 승인 전 세부 필드 확정 금지
# 코드 경계: LLM·RAG 내부 구현을 직접 import하지 않는다. 확인된 근거 없는 본문 공개를 금지한다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A08 요청 모양 (openapi.yaml A08_askAi requestBody). JSON 이름은 camelCase(I01)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AskRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    # 길이는 Python 문자열 길이(= Unicode 코드 포인트 수)로 센다. 빈 질문은 서비스 정책에서 거부한다.
    question: str = Field(max_length=200)
    request_id: str = Field(min_length=1)
    previous_questions: list[str] = Field(default_factory=list, max_length=3)
