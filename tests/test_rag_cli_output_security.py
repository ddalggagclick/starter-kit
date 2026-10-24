from __future__ import annotations

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from starter_rag import cli as rag_cli
from starter_rag.contracts.models import Evidence, SearchResult, SourceRef
from starter_rag.retrieval import search as search_module
from starter_rag.storage.database import DatabaseConfigurationError

SYNTHETIC_QUERY = "합성 개인정보 점검 홍길동 qa.synthetic@example.invalid 010-0000-0000"
FAKE_DATABASE_URL = "postgresql://qa:FAKE_PASSWORD_ONLY@db.invalid/rag"


def _configure_search(monkeypatch, result_or_error):
    database = object()
    monkeypatch.setattr(rag_cli, "_database_for_profile", AsyncMock(return_value=database))
    monkeypatch.setattr(rag_cli, "_release_profile_database", AsyncMock())
    monkeypatch.setattr(
        rag_cli,
        "PGVectorStore",
        lambda *_args, **_kwargs: SimpleNamespace(embedding=object()),
    )
    monkeypatch.setattr(rag_cli, "EmbeddingGemma", lambda: object())

    class StubSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        async def search(self, _request):
            if isinstance(result_or_error, BaseException):
                raise result_or_error
            return result_or_error

    monkeypatch.setattr(search_module, "PGVectorSearch", StubSearch)


def _run_cli_search(query: str = SYNTHETIC_QUERY) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = rag_cli.main(["search", query, "--collection-id", "isolated-synthetic-test"])
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _example_evidence() -> Evidence:
    return Evidence(
        evidence_id="chunk-synthetic-01",
        source=SourceRef(
            source_id="synthetic-guide-01",
            title="합성 상속 안내",
            url="https://example.invalid/guide",
            publisher="합성 발행기관",
            version="sha256-test-version",
        ),
        text="합성 안내 문서 본문입니다.",
        location="page:1",
        score=0.75,
    )


def test_search_success_does_not_echo_query_or_change_evidence_contract(monkeypatch):
    _configure_search(monkeypatch, SearchResult((_example_evidence(),)))

    exit_code, stdout, stderr = _run_cli_search()

    assert exit_code == 0
    assert stderr == ""
    assert SYNTHETIC_QUERY not in stdout
    assert "qa.synthetic@example.invalid" not in stdout
    assert "010-0000-0000" not in stdout
    payload = json.loads(stdout)
    assert "query" not in payload
    assert payload["evidence"][0] == {
        "evidence_id": "chunk-synthetic-01",
        "source": {
            "source_id": "synthetic-guide-01",
            "title": "합성 상속 안내",
            "url": "https://example.invalid/guide",
            "publisher": "합성 발행기관",
            "version": "sha256-test-version",
        },
        "text": "합성 안내 문서 본문입니다.",
        "location": "page:1",
        "score": 0.75,
    }


def test_search_empty_result_does_not_echo_query(monkeypatch):
    _configure_search(monkeypatch, SearchResult(()))

    exit_code, stdout, stderr = _run_cli_search()

    assert exit_code == 0
    assert stderr == ""
    assert SYNTHETIC_QUERY not in stdout
    assert "qa.synthetic@example.invalid" not in stdout
    payload = json.loads(stdout)
    assert "query" not in payload
    assert payload["evidence"] == []


def test_search_error_does_not_echo_query_exception_or_database_credentials(monkeypatch):
    _configure_search(
        monkeypatch,
        RuntimeError(f"query={SYNTHETIC_QUERY}; url={FAKE_DATABASE_URL}"),
    )

    exit_code, stdout, stderr = _run_cli_search()

    assert exit_code == 1
    assert stdout == ""
    assert "RAG 검색 실패: RuntimeError" in stderr
    assert SYNTHETIC_QUERY not in stderr
    assert "qa.synthetic@example.invalid" not in stderr
    assert "010-0000-0000" not in stderr
    assert FAKE_DATABASE_URL not in stderr
    assert "FAKE_PASSWORD_ONLY" not in stderr


def test_search_configuration_error_does_not_print_exception_message(monkeypatch):
    _configure_search(
        monkeypatch,
        DatabaseConfigurationError(f"{SYNTHETIC_QUERY}; {FAKE_DATABASE_URL}"),
    )

    exit_code, stdout, stderr = _run_cli_search()

    assert exit_code == 2
    assert stdout == ""
    assert "DatabaseConfigurationError" in stderr
    assert SYNTHETIC_QUERY not in stderr
    assert "qa.synthetic@example.invalid" not in stderr
    assert "010-0000-0000" not in stderr
    assert FAKE_DATABASE_URL not in stderr
    assert "FAKE_PASSWORD_ONLY" not in stderr
