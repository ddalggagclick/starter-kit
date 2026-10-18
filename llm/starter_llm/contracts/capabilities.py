# 담당: [C] | 책임: 공급자가 지원하는 모델 기능의 공개 계약.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (공개 계약 지원)
# 구현할 기능: 구조화 출력, 스트림, 취소 지원 여부를 명시한다.
# 완료 기준: 지원하지 않는 기능을 호출 전에 식별할 수 있다.
# 제한사항: 공급자별 API 호출과 HTTP 전송 규격을 이 파일에 두지 않는다.
"""[C] 공급자 기능 계약. 구현할 기능: 구조화 출력·스트림·취소 지원 여부를 명시.
경계: 모델 이름만 바꿔도 모든 기능이 동일하다고 가정하지 않는다.
완료: 미지원 기능 호출은 조용한 무시 없이 UNSUPPORTED_CAPABILITY 오류.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    streaming: bool
    structured_output: bool
    cancellation: bool
    max_context_tokens: int | None = None
