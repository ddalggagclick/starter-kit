# 담당: [통합] | 책임: User와 RefreshSession의 인증 자료형.
# PRD: E5 / 스토리 5-1, 5-2 / 태스크 5-1-2, 5-2-3
# 구현할 기능: 비밀번호 해시와 Refresh 세션 상태를 저장한다.
# 완료 기준: 비밀번호 원문을 저장하지 않고 승인된 인증 모델을 사용한다.
# 제한사항: ERD와 마이그레이션 승인 전 테이블 구조를 추가하지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""인증 자료형. ERD 승인 전이라 메모리 저장소에서만 쓴다. 비밀번호·토큰 원문은 담지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OneTimeKind = Literal["email_verify", "password_reset"]


@dataclass
class User:
    user_id: str
    email: str
    password_hash: str
    verified: bool = False


@dataclass
class RefreshSession:
    token_hash: str
    user_id: str
    family_id: str
    expires_at: float
    used: bool = False
    revoked: bool = False


@dataclass
class OneTimeToken:
    token_hash: str
    kind: OneTimeKind
    user_id: str
    expires_at: float
    used: bool = False
