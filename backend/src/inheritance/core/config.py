# 담당: [통합] | 책임: Backend 환경 설정과 필수값 검증.
# PRD: E7 / 스토리 7-3 / 태스크 7-3-3 (인증 설정 지원: 5-2-2)
# 구현할 기능: DB 연결, 허용 Origin, 자체 JWT·CSRF·Refresh 및 모델 설정을 읽는다.
# 완료 기준: 업무 의존성을 조립할 때 누락되거나 유효하지 않은 설정을 거부한다.
# 현재 상태: health 전용 앱은 DB·인증 설정을 읽지 않는다.
# 제한사항: Supabase Auth로 대체하지 않는다. 미승인 DB 스키마와 인증 정책을 정하지 않는다.
"""운영 설정은 명시적 진입점에서만 읽는다. `.env` 로더는 앱 실행 도구가 담당."""

from __future__ import annotations

import re
from dataclasses import dataclass
from os import environ
from urllib.parse import urlsplit

from .origin import DEFAULT_FRONTEND_ORIGIN, is_exact_http_origin


def _int_env(name: str, default: int, *, min_value: int = 0) -> int:
    raw = environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    value = environ.get(name, "true" if default else "false").lower()
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    return value == "true"


_SQL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True)
class Settings:
    app_env: str

    database_url: str
    backend_db_schema: str
    rag_db_schema: str
    rag_vector_table: str
    rag_collection_id: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout_seconds: int

    frontend_origin: str
    auth_signup_enabled: bool
    auth_login_enabled: bool
    jwt_signing_key: str
    csrf_secret: str
    handoff_hash_key: str
    handoff_server_secret: str
    jwt_issuer: str
    jwt_audience: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    refresh_rotation_enabled: bool
    refresh_cookie_httponly: bool
    refresh_cookie_secure: bool
    refresh_cookie_samesite: str
    password_hash_scheme: str
    chat_rate_limit_per_minute: int
    login_failure_limit: int
    login_failure_window_seconds: int
    handoff_ttl_seconds: int

    llm_provider: str
    llm_model: str
    classifier_provider: str
    classifier_model: str
    llm_auto_fallback: bool
    model_client_idle_seconds: int

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            app_env=environ.get("APP_ENV", "development"),
            database_url=environ.get("DATABASE_URL", ""),
            backend_db_schema=environ.get("BACKEND_DB_SCHEMA", "app"),
            rag_db_schema=environ.get("RAG_DB_SCHEMA", "rag"),
            rag_vector_table=environ.get("RAG_VECTOR_TABLE", "chunks"),
            rag_collection_id=environ.get("RAG_COLLECTION_ID", ""),
            db_pool_size=_int_env("DB_POOL_SIZE", 2, min_value=1),
            db_max_overflow=_int_env("DB_MAX_OVERFLOW", 0),
            db_pool_timeout_seconds=_int_env("DB_POOL_TIMEOUT_SECONDS", 10, min_value=1),
            frontend_origin=environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
            auth_signup_enabled=_bool_env("AUTH_SIGNUP_ENABLED", True),
            auth_login_enabled=_bool_env("AUTH_LOGIN_ENABLED", True),
            jwt_signing_key=environ.get("JWT_SIGNING_KEY", ""),
            csrf_secret=environ.get("CSRF_SECRET", ""),
            handoff_hash_key=environ.get("HANDOFF_HASH_KEY", ""),
            handoff_server_secret=environ.get("HANDOFF_SERVER_SECRET", ""),
            jwt_issuer=environ.get("JWT_ISSUER", "inheritance-backend"),
            jwt_audience=environ.get("JWT_AUDIENCE", "inheritance-web"),
            access_token_ttl_seconds=_int_env("ACCESS_TOKEN_TTL_SECONDS", 900, min_value=1),
            refresh_token_ttl_seconds=_int_env("REFRESH_TOKEN_TTL_SECONDS", 604800, min_value=1),
            refresh_rotation_enabled=_bool_env("REFRESH_ROTATION_ENABLED", True),
            refresh_cookie_httponly=_bool_env("REFRESH_COOKIE_HTTPONLY", True),
            refresh_cookie_secure=_bool_env("REFRESH_COOKIE_SECURE", True),
            refresh_cookie_samesite=environ.get("REFRESH_COOKIE_SAMESITE", "none").lower(),
            password_hash_scheme=environ.get("PASSWORD_HASH_SCHEME", "argon2id"),
            chat_rate_limit_per_minute=_int_env("CHAT_RATE_LIMIT_PER_MINUTE", 10, min_value=1),
            login_failure_limit=_int_env("LOGIN_FAILURE_LIMIT", 5, min_value=1),
            login_failure_window_seconds=_int_env("LOGIN_FAILURE_WINDOW_SECONDS", 900, min_value=1),
            handoff_ttl_seconds=_int_env("HANDOFF_TTL_SECONDS", 600, min_value=1),
            llm_provider=environ.get("LLM_PROVIDER", "gemini"),
            llm_model=environ.get("LLM_MODEL", "gemini-3.5-flash-lite"),
            classifier_provider=environ.get("CLASSIFIER_PROVIDER", "gemini"),
            classifier_model=environ.get("CLASSIFIER_MODEL", "gemini-3.5-flash-lite"),
            llm_auto_fallback=_bool_env("LLM_AUTO_FALLBACK", False),
            model_client_idle_seconds=_int_env("MODEL_CLIENT_IDLE_SECONDS", 300, min_value=1),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_env not in ("development", "test", "production"):
            raise ValueError("APP_ENV must be development/test/production")
        self._validate_database()
        self._validate_origin()
        self._validate_auth()
        self._validate_model()

    # DB URL의 scheme·port를 확인하고 운영에서는 Supabase Session Pooler 형식을 요구한다.
    def _validate_database(self) -> None:
        try:
            url = urlsplit(self.database_url)
            port = url.port
        except ValueError:
            raise ValueError(
                "DATABASE_URL must be postgresql+asyncpg Session Pooler port 5432"
            ) from None
        if url.scheme != "postgresql+asyncpg" or not url.hostname or port != 5432:
            raise ValueError("DATABASE_URL must be postgresql+asyncpg Session Pooler port 5432")
        if not url.hostname.endswith(".pooler.supabase.com"):
            raise ValueError("DATABASE_URL must use Supabase Session Pooler")
        if self.production and (
            not url.username or not url.username.startswith("postgres.") or not url.password
        ):
            raise ValueError("production Session Pooler requires dashboard username/password")
        identifiers = (self.backend_db_schema, self.rag_db_schema, self.rag_vector_table)
        if any(_SQL_IDENTIFIER.fullmatch(value) is None for value in identifiers):
            raise ValueError("schema/table names must be simple SQL identifiers")
        if self.rag_db_schema != "rag" or self.rag_vector_table != "chunks":
            raise ValueError("RAG_DB_SCHEMA=rag and RAG_VECTOR_TABLE=chunks are required")
        if self.rag_collection_id and not self.rag_collection_id.strip():
            raise ValueError("RAG_COLLECTION_ID must be a non-empty value when set")

    def _validate_origin(self) -> None:
        if not is_exact_http_origin(self.frontend_origin):
            raise ValueError("FRONTEND_ORIGIN must be an exact origin")
        if self.production and urlsplit(self.frontend_origin).scheme != "https":
            raise ValueError("production FRONTEND_ORIGIN must be https")

    def _validate_auth(self) -> None:
        if self.refresh_cookie_samesite not in ("none", "lax", "strict"):
            raise ValueError("REFRESH_COOKIE_SAMESITE invalid")
        if self.production and (
            not self.refresh_cookie_secure
            or not self.refresh_cookie_httponly
            or self.refresh_cookie_samesite != "none"
        ):
            raise ValueError("production cross-site cookie requires HttpOnly Secure SameSite=None")
        if self.password_hash_scheme != "argon2id":
            raise ValueError("PASSWORD_HASH_SCHEME must be argon2id")
        if self.production and any(
            len(value) < 32
            for value in (
                self.jwt_signing_key,
                self.csrf_secret,
                self.handoff_hash_key,
                self.handoff_server_secret,
            )
        ):
            raise ValueError("production JWT/CSRF/Handoff secrets must be >=32 characters")
        if not self.refresh_rotation_enabled:
            raise ValueError("rotating refresh token policy is required")

    def _validate_model(self) -> None:
        if self.llm_auto_fallback:
            raise ValueError("Gemini API rate limit may not trigger automatic fallback")
        if self.llm_provider not in ("gemini", "ollama") or self.classifier_provider not in (
            "gemini",
            "ollama",
        ):
            raise ValueError("invalid explicit provider")
