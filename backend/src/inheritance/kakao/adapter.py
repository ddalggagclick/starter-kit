# 담당: [C] | 책임: 카카오 Skill JSON을 공통 체크리스트 입력으로 변환한다.
# PRD: E1 / 스토리 1-1 / 태스크 1-1-2.
# 구현할 기능: 공식 입력에서 초기 답변을 정규화하고 누락·알 수 없는 선택지를 구분한다.
# 완료 기준: 정상 입력은 InitialAnswers로 변환되고 잘못된 값은 검증 오류가 된다.
# 제한사항: 원시 카카오 JSON을 B1 서비스에 넘기지 않는다. '모름'을 '아니요'로 바꾸지 않는다.
# 상태: PRD 태스크 미시작.
"""실제 카카오 필드 매핑은 C 담당자가 공식 스킬 JSON 테스트로 구현한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from inheritance.contracts.checklist import RecommendationInput


class KakaoInputAdapter(Protocol):
    # 공식 Skill 요청을 내부 입력 DTO로 바꾸고, 지원하지 않는 답변 값은 검증 오류로 거부한다.
    def parse(self, skill_request: Mapping[str, Any]) -> RecommendationInput: ...
