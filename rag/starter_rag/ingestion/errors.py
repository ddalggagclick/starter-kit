# 담당: [D] | 책임: RAG 수집 단계에서 공유하는 입력·투영 오류.
# 구현할 기능: 파서·투영 어댑터가 같은 예외 타입을 사용한다.
# 완료 기준: 모듈 재적재 뒤에도 호출자와 제공자의 예외 타입이 일치한다.
"""Shared errors for RAG document ingestion."""


class ProjectionError(ValueError):
    """Input cannot be projected into a verified, stable chunk."""
