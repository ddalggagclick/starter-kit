# 담당: [C] | 책임: 카카오→웹 Handoff 발급 정책.
# PRD: E1 / 스토리 1-4 / 태스크 1-4-1.
# 구현할 기능: 최소 답변으로 불투명 토큰을 발급하고 10분 안에 한 번만 사용할 수 있게 한다.
# 완료 기준: 발급 자료에 카카오 사용자 ID 원문이나 불필요한 개인정보가 없다.
# 제한사항: Handoff는 로그인 JWT가 아니다. 원자적 소비 Task 1-4-2는 B1·통합 담당이며 소유권을 이 파일에 합치지 않는다.
# 상태: PRD 태스크 미시작. 저장 방식 충돌은 별도 확인이 필요하다.
"""A04 발급·A05 교환 정책. 비밀값 확인과 저장소 호출만 한다."""

from __future__ import annotations

import hmac
import os

from inheritance.kakao.handoff.models import HandoffPayload
from inheritance.kakao.handoff.repository import InMemoryHandoffStore, SignedHandoffStore


class HandoffUnauthorized(Exception):
    pass


class HandoffInvalid(Exception):
    pass


class HandoffService:
    def __init__(
        self, store: InMemoryHandoffStore | SignedHandoffStore, secret: str | None = None
    ) -> None:
        self._store = store
        self._secret = secret

    def _expected_secret(self) -> str:
        if self._secret is not None:
            return self._secret
        return os.environ.get("HANDOFF_SERVER_SECRET", "")

    # 비밀값이 설정되지 않은 서버는 모든 발급을 거절한다 (빈 값끼리 통과하는 실수 방지).
    def issue(self, payload: HandoffPayload, given_secret: str | None) -> str:
        expected = self._expected_secret()
        if (
            not expected
            or given_secret is None
            or not hmac.compare_digest(given_secret.encode(), expected.encode())
        ):
            raise HandoffUnauthorized
        return self._store.issue(payload.model_dump(mode="json", by_alias=True))

    def purge_expired(self) -> None:
        self._store.purge_expired()

    # 만료·이미 사용·없는 토큰을 구분하지 않는다 (D1).
    def exchange(self, token: str) -> dict:
        payload = self._store.consume(token)
        if payload is None:
            raise HandoffInvalid
        return payload
