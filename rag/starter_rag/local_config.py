# 담당: [D] | 책임: 관리자 CLI의 로컬 설정을 비공개 파일에 보관한다.
# 구현할 기능: 환경변수 우선 적용, 로컬 DB URL 검증, 안전한 설정 표시.
# 완료 기준: 설정 파일은 저장소 밖에 0600 권한으로 저장되고 비밀값이 출력되지 않는다.
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from starter_rag.storage.database import (
    DatabaseConfigurationError,
    database_url_from_environment,
)

CONFIG_KEYS = frozenset(
    {
        "RAG_DATABASE_URL",
        "RAG_LOCAL_DATABASE_NAME",
        "RAG_TOKENIZER_PATH",
        "RAG_CHUNKING_PROVIDER",
        "RAG_CHUNKING_MODEL",
        "RAG_CHUNKING_OLLAMA_BASE_URL",
        "RAG_CHUNKING_CONTEXT_TOKENS",
        "RAG_CHUNKING_RESPONSE_RESERVE_TOKENS",
        "RAG_SEARCH_CANDIDATE_COUNT",
    }
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    """Local settings are missing, malformed, or stored unsafely."""


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    return Path(
        values.get("RAG_CONFIG_PATH", str(Path.home() / ".config" / "starter-rag" / "config.json"))
    ).expanduser()


def _read_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise ConfigError("RAG 설정 파일 권한을 0600으로 변경하세요.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ConfigError("RAG 설정 파일을 읽을 수 없습니다.") from None
    if not isinstance(data, dict) or any(
        key not in CONFIG_KEYS or not isinstance(value, str) for key, value in data.items()
    ):
        raise ConfigError("RAG 설정 파일 형식이 올바르지 않습니다.")
    return data


def effective_config(path: Path, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if environ is None else environ
    saved = _read_config(path)
    saved.update({key: values[key] for key in CONFIG_KEYS if key in values})
    return saved


def validate_config(settings: Mapping[str, str]) -> None:
    try:
        database_url_from_environment(settings)
    except DatabaseConfigurationError:
        raise ConfigError("로컬 RAG DB 연결 문자열과 승인 DB 이름을 확인하세요.") from None
    provider = settings.get("RAG_CHUNKING_PROVIDER")
    model = settings.get("RAG_CHUNKING_MODEL")
    if provider is not None and provider != "ollama":
        raise ConfigError("로컬 설정에는 Ollama 청킹 공급자만 저장할 수 있습니다.")
    if provider == "ollama" and not model:
        raise ConfigError("RAG_CHUNKING_MODEL이 필요합니다.")
    tokenizer = settings.get("RAG_TOKENIZER_PATH")
    if tokenizer is not None and not tokenizer.strip():
        raise ConfigError("RAG_TOKENIZER_PATH가 비어 있습니다.")
    candidate_count = settings.get("RAG_SEARCH_CANDIDATE_COUNT")
    if candidate_count is not None:
        try:
            valid_candidate_count = 1 <= int(candidate_count) <= 10
        except ValueError:
            valid_candidate_count = False
        if not valid_candidate_count:
            raise ConfigError("RAG_SEARCH_CANDIDATE_COUNT는 1~10 사이여야 합니다.")


def save_config_from_environment(path: Path, environ: Mapping[str, str]) -> None:
    values = {key: environ[key] for key in CONFIG_KEYS if key in environ}
    validate_config(values)
    path = path.expanduser().resolve()
    if path.is_relative_to(REPOSITORY_ROOT):
        raise ConfigError("설정 파일을 저장소 밖의 개인 경로에 저장하세요.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".config-", delete=False
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            json.dump(values, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def display_config(settings: Mapping[str, str]) -> dict[str, str]:
    result = dict(settings)
    raw_url = result.get("RAG_DATABASE_URL")
    if raw_url:
        try:
            url = make_url(raw_url)
            host = url.host or "local socket"
            result["RAG_DATABASE_URL"] = f"{url.drivername}://***@{host}/{url.database or '?'}"
        except (ArgumentError, ValueError):
            result["RAG_DATABASE_URL"] = "<invalid>"
    return result
