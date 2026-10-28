# 담당: [통합] | 책임: Argon2id 비밀번호 해시와 검증.
# PRD: E5 / 스토리 5-1 / 태스크 5-1-2
# 구현할 기능: 비밀번호를 해시하고 해시와 입력값을 검증한다.
# 완료 기준: 비밀번호 원문을 저장하거나 로그에 남기지 않는다.
# 제한사항: 미확정 비밀번호 길이·복잡도 정책을 임의로 정하지 않는다.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행한다.
"""Argon2id 비밀번호 해시(pwdlib). 정책: 8~64자, 영문·숫자 조합(openapi A11 H5)."""

from __future__ import annotations

import re

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

_HASHER = PasswordHash((Argon2Hasher(),))
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


def password_policy_ok(password: str) -> bool:
    return (
        8 <= len(password) <= 64
        and _HAS_LETTER.search(password) is not None
        and _HAS_DIGIT.search(password) is not None
    )


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _HASHER.verify(password, password_hash)
