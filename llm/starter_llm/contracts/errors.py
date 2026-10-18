# 담당: [C] | 책임: 공급자 오류를 LLM 공개 오류 코드로 정규화.
# PRD: E3 / 스토리 3-2 / 태스크 3-2-4
# 구현할 기능: 시간 초과, 사용량 제한, 공급자 불가, 잘못된 출력과 취소를 구분한다.
# 완료 기준: 호출 측이 제한된 오류 코드로 다음 처리를 선택할 수 있다.
# 제한사항: 자격 증명, 프롬프트, 사용자 원문을 오류에 포함하지 않는다.
"""[C] LLM 오류 계약. 구현할 기능: provider 실패를 제한된 코드로 정규화.
경계: 자격증명·프롬프트·원문을 예외 메시지에 포함하지 않는다.
완료: 모델 미지원·시간초과·호출 제한·출력 위반을 구분한다.
"""

from enum import StrEnum


class ModelErrorCode(StrEnum):
    TIMEOUT = "MODEL_TIMEOUT"
    RATE_LIMIT = "MODEL_RATE_LIMIT"
    UNAVAILABLE = "MODEL_UNAVAILABLE"
    INVALID_OUTPUT = "MODEL_INVALID_OUTPUT"
    UNSUPPORTED_CAPABILITY = "MODEL_UNSUPPORTED_CAPABILITY"
    CANCELLED = "MODEL_CANCELLED"


class ModelError(Exception):
    def __init__(self, code: ModelErrorCode, request_id: str, retryable: bool = False):
        self.code, self.request_id, self.retryable = code, request_id, retryable
        super().__init__(code.value)
