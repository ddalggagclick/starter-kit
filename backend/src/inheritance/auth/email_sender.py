# 담당: [통합] 영역, 구현 B1 김현주(통합 허용) | 책임: 인증·비밀번호 재설정 메일을 SMTP로 보낸다.
# PRD: E5 / 스토리 5-2 / 태스크 5-2-1 (A12·A15 메일).
# 구현할 기능: 1회용 링크 메일을 보내고 실패해도 가입 여부·토큰을 드러내지 않는다.
# 완료 기준: 토큰·비밀번호·SMTP 비밀값이 로그와 오류에 남지 않는다.
# 제한사항: 메일 링크의 웹 화면 경로(/auth/verify, /auth/reset)는 프론트 담당 확인 전 제안값이다.
"""SMTP 메일 발송기(2026-10-23 팀 결정: SMTP). 표준 라이브러리 smtplib만 쓴다.

링크의 토큰은 주소의 `#` 뒤(fragment)에 둔다. 브라우저가 서버로 보내지 않아 서버 로그·Referer에 남지 않는다.
발송 실패는 요청을 실패시키지 않는다(사용자는 재전송할 수 있다). 로그에는 허용 필드만 남긴다(7-4-3).
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger(__name__)

VERIFY_PATH = "/auth/verify"
RESET_PATH = "/auth/reset"
SMTP_TIMEOUT_SECONDS = 10.0
_SSL_PORT = 465


class SmtpEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        frontend_origin: str,
        username: str = "",
        password: str = "",
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._origin = frontend_origin.rstrip("/")
        self._username = username
        self._password = password
        self._factory = smtp_factory

    def send_verification(self, email: str, token: str) -> None:
        link = f"{self._origin}{VERIFY_PATH}#token={token}"
        body = (
            "상속길잡이 가입을 마치려면 아래 링크를 열어 이메일 인증을 완료하세요.\n"
            f"{link}\n\n"
            "링크는 24시간 동안 한 번만 사용할 수 있습니다. 본인이 가입하지 않았다면 이 메일을 무시하세요."
        )
        self._send(email, "[상속길잡이] 이메일 인증", body, "verify")

    def send_password_reset(self, email: str, token: str) -> None:
        link = f"{self._origin}{RESET_PATH}#token={token}"
        body = (
            "아래 링크에서 새 비밀번호를 설정하세요.\n"
            f"{link}\n\n"
            "링크는 30분 동안 한 번만 사용할 수 있습니다. 본인이 요청하지 않았다면 이 메일을 무시하세요."
        )
        self._send(email, "[상속길잡이] 비밀번호 재설정", body, "reset")

    def _send(self, to: str, subject: str, body: str, kind: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with self._connect() as smtp:
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # 받는 주소·토큰·서버 응답 문구는 남기지 않는다. 예외 종류 이름만 남긴다.
            logger.warning(
                "auth.email",
                extra={
                    "event": f"auth.email.{kind}",
                    "status": "failed",
                    "error_code": type(exc).__name__,
                },
            )
            return
        logger.info("auth.email", extra={"event": f"auth.email.{kind}", "status": "sent"})

    # 465는 처음부터 TLS, 그 밖(587 등)은 STARTTLS로 올린다. 암호화 없는 발송은 하지 않는다.
    def _connect(self) -> Any:
        context = ssl.create_default_context()
        if self._factory is not None:
            smtp = self._factory(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS)
            smtp.starttls(context=context)
            return smtp
        if self._port == _SSL_PORT:
            return smtplib.SMTP_SSL(
                self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        smtp = smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS)
        smtp.starttls(context=context)
        return smtp


# SMTP_HOST·SMTP_FROM이 없으면 None(메일을 보내지 않는 기본값을 쓴다).
def smtp_sender_from_env(frontend_origin: str) -> SmtpEmailSender | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip()
    if not host or not sender:
        return None
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        return None
    return SmtpEmailSender(
        host=host,
        port=port,
        sender=sender,
        frontend_origin=frontend_origin,
        username=os.environ.get("SMTP_USERNAME", ""),
        password=os.environ.get("SMTP_PASSWORD", ""),
    )
