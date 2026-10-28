# 담당: [C] | 책임: 카카오 입력을 공통 안내 입력으로 변환한다.
# PRD: E1 / 스토리 1-1 / 태스크 1-1-2.
# 구현할 기능: 공식 입력에서 초기 답변을 정규화하고 누락·알 수 없는 선택지를 구분한다.
# 완료 기준: 정상 입력은 InitialAnswers로 변환되고 잘못된 값은 검증 오류가 된다.
# 제한사항: 원시 카카오 JSON을 B1 서비스에 넘기지 않는다. '모름'을 '아니요'로 바꾸지 않는다.
# 상태: 구현됨(JsonKakaoInputAdapter). 시험: tests/test_kakao_input_adapter.py.
"""카카오 스킬 요청 JSON을 공통 안내 입력(GuidanceInput)으로 변환한다.

답은 오픈빌더 파라미터(요청의 action.params)에서 읽는다. 이름은 A04 본문과 같다:
relationship, deathDate, deathDateUnknown, oneStopApplication, risks.
오픈빌더 파라미터 값은 문자열이므로 deathDateUnknown은 "true"/"false",
risks는 JSON 문자열(또는 목록)을 받는다. 원시 카카오 JSON은 이 파일 밖으로 나가지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol

from inheritance.contracts.checklist import GuidanceInput
from inheritance.contracts.domain import InitialAnswers, RiskAnswer


class KakaoInputAdapter(Protocol):
    # 카카오 요청에서 초기·위험 답변을 추출해 GuidanceInput으로 변환한다
    def parse(self, skill_request: Mapping[str, Any]) -> GuidanceInput: ...


class KakaoInputError(ValueError):
    """입력 오류(HTTP에서는 422 VALIDATION_ERROR). 메시지에는 필드 이름만 담고 입력값은 담지 않는다."""

    def __init__(self, field: str) -> None:
        super().__init__(f"invalid or missing field: {field}")
        self.field = field


class JsonKakaoInputAdapter:
    def parse(self, skill_request: Mapping[str, Any]) -> GuidanceInput:
        params = self._params(skill_request)
        relationship = self._required(params, "relationship")
        one_stop = self._required(params, "oneStopApplication")
        death_date, unknown = self._death(params)
        risks = self._risks(params.get("risks"))
        try:
            initial = InitialAnswers(
                relationship=relationship,  # type: ignore[arg-type]
                death_date=death_date,
                death_date_unknown=unknown,
                one_stop_application=one_stop,  # type: ignore[arg-type]
            )
        except ValueError:
            raise KakaoInputError(self._bad_field(relationship, one_stop)) from None
        try:
            return GuidanceInput(initial, risks)
        except ValueError:
            raise KakaoInputError("risks") from None

    @staticmethod
    def _params(request: Mapping[str, Any]) -> Mapping[str, Any]:
        action = request.get("action") if isinstance(request, Mapping) else None
        params = action.get("params") if isinstance(action, Mapping) else None
        if not isinstance(params, Mapping):
            raise KakaoInputError("action.params")
        return params

    @staticmethod
    def _required(params: Mapping[str, Any], name: str) -> str:
        value = params.get(name)
        if not isinstance(value, str) or not value:
            raise KakaoInputError(name)
        return value

    @staticmethod
    def _death(params: Mapping[str, Any]) -> tuple[str | None, bool]:
        raw_unknown = params.get("deathDateUnknown")
        if raw_unknown not in ("true", "false", True, False):
            raise KakaoInputError("deathDateUnknown")
        unknown = raw_unknown in ("true", True)
        raw_date = params.get("deathDate")
        if unknown:
            if raw_date not in (None, ""):
                raise KakaoInputError("deathDate")
            return None, True
        if not isinstance(raw_date, str):
            raise KakaoInputError("deathDate")
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            raise KakaoInputError("deathDate") from None
        if parsed.isoformat() != raw_date or parsed > date.today():
            raise KakaoInputError("deathDate")
        return raw_date, False

    @staticmethod
    def _risks(raw: Any) -> tuple[RiskAnswer, ...]:
        # 비어 있으면 '미응답'이다. '아니요'로 바꾸지 않는다.
        if raw in (None, "", []):
            return ()
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raise KakaoInputError("risks") from None
        if not isinstance(raw, list) or len(raw) > 3:
            raise KakaoInputError("risks")
        answers = []
        for item in raw:
            if not isinstance(item, Mapping) or set(item) != {"riskId", "answer"}:
                raise KakaoInputError("risks")
            try:
                answers.append(RiskAnswer(item["riskId"], item["answer"]))
            except ValueError:
                raise KakaoInputError("risks") from None
        return tuple(answers)

    @staticmethod
    def _bad_field(relationship: str, one_stop: str) -> str:
        if relationship not in ("spouse", "descendant", "ascendant", "sibling", "other", "unknown"):
            return "relationship"
        if one_stop not in ("yes", "no", "unknown"):
            return "oneStopApplication"
        return "deathDate"
