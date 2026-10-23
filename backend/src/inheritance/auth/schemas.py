# 담당: [통합] | 책임: [통합] 인증용 Pydantic API 스키마 자리
# 구현할 기능: API 계약 담당자 승인 후 필드 정의; 내부 DTO와 API DTO 변환
# 코드 경계: 계정·토큰·세션만 다룬다. 상속 규칙·채팅 원문을 저장하지 않는다.
# 완료 기준: 담당자가 확정한 OpenAPI와 오류 케이스 계약 테스트 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
# 계약 합의가 끝나면 이 파일에 구현합니다.
"""A11~A16 요청·응답 모양 (openapi.yaml auth·account). JSON 이름은 camelCase(I01)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SignupRequest(CamelModel):
    email: EmailStr
    # 영문·숫자 조합 검사는 auth/password.py가 한다(H5).
    password: str = Field(min_length=8, max_length=64)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class EmailRequest(CamelModel):
    email: EmailStr


class VerifyEmailRequest(CamelModel):
    verification_token: str = Field(min_length=1, max_length=256)


class ResetPasswordRequest(CamelModel):
    reset_token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=64)


class DeleteAccountRequest(CamelModel):
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(CamelModel):
    access_token: str
    expires_in: int


class RefreshResponse(CamelModel):
    access_token: str


class CsrfResponse(CamelModel):
    csrf_token: str
