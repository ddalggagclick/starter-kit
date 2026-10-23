# 담당: [통합] | 책임: Access JWT 발급과 서명 검증.
# PRD: E5 / 스토리 5-2 / 태스크 5-2-2
# 구현할 기능: issuer, audience, 만료 시각, 서명 및 키 식별자를 검증한다.
# 완료 기준: 승인된 JWT 계약에 맞지 않는 토큰을 거부한다.
# 제한사항: Supabase Auth로 대체하지 않는다. 비밀값과 토큰을 로그에 남기지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""Access JWT(HS256, 15분). sub=사용자 ID, iss·aud·exp·iat·jti를 검증한다."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import jwt

_ALGORITHM = "HS256"


class AccessTokenInvalid(Exception):
    pass


@dataclass(frozen=True)
class AccessTokenCodec:
    signing_key: str
    issuer: str = "inheritance-backend"
    audience: str = "inheritance-web"
    ttl_seconds: int = 900

    def issue(self, user_id: str, now: int) -> str:
        claims = {
            "sub": user_id,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": now,
            "exp": now + self.ttl_seconds,
            "jti": secrets.token_urlsafe(12),
        }
        return jwt.encode(claims, self.signing_key, algorithm=_ALGORITHM)

    # 서명·만료·발급자·대상이 하나라도 맞지 않으면 거부한다. 원인은 밖으로 내보내지 않는다.
    def verify(self, token: str) -> str:
        try:
            claims = jwt.decode(
                token,
                self.signing_key,
                algorithms=[_ALGORITHM],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWTError:
            raise AccessTokenInvalid from None
        return str(claims["sub"])
