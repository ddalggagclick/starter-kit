# 책임: [통합] Frontend Origin의 정확한 주소 형식을 검증한다.
# PRD: E7 / 스토리 7-3 / 태스크 7-3-3 (인증 설정 지원: 5-2-2)
# 구현할 기능: 설정 검증과 CORS 설치가 같은 Origin 규칙을 사용한다.
# 완료 기준: 경로·인증정보·와일드카드가 포함된 주소를 거부한다.

from __future__ import annotations

from urllib.parse import urlsplit

DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"


# 경로·인증정보·쿼리·조각이 없는 정확한 HTTP(S) Origin만 허용한다.
def is_exact_http_origin(value: str) -> bool:
    if value != value.strip() or any(char in value for char in "*?#") or value.endswith("/"):
        return False
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        return False
    return (
        url.scheme in {"http", "https"}
        and bool(url.hostname)
        and (port is None or port > 0)
        and not url.netloc.endswith(":")
        and not url.path
        and not url.query
        and not url.fragment
        and url.username is None
        and url.password is None
    )
