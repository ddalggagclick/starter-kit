from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import DBAPIError
from starter_rag import cli as rag_cli
from starter_rag.contracts.models import ChunkRecord, DocumentVersion, SourceRef
from starter_rag.storage.database import DatabaseConfigurationError, PostgresRagDatabase
from starter_rag.storage.publication import (
    PostgresPublicationStore,
    PublicationError,
    PublicationInspection,
    PublicationOutcome,
    ReplacementApprovalRequired,
)
from starter_rag.storage.vector_store import PGVectorStore


def _connection_error() -> DBAPIError:
    return DBAPIError(
        "SELECT 1",
        {},
        Exception("postgresql://rag-user:secret@db.example.invalid/rag"),
        connection_invalidated=True,
    )


def _sqlstate_error(sqlstate: str, *, nested: bool = False, detail: str = "") -> DBAPIError:
    driver_error = RuntimeError(detail)
    driver_error.sqlstate = sqlstate  # type: ignore[attr-defined]
    original: Exception = driver_error
    if nested:
        original = RuntimeError("driver wrapper")
        original.__cause__ = driver_error
    return DBAPIError("SELECT 1", {}, original, connection_invalidated=False)


class _FakePublicationStore:
    def __init__(
        self,
        states: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.states = dict(states or {})
        self.publish_calls: list[tuple[str, str, bool]] = []
        self.inspect_calls: dict[str, int] = {}
        self.publish_errors: dict[str, list[Exception]] = {}
        self.ambiguous_commit: set[str] = set()
        self.outage_after_publish: set[str] = set()
        self.published_attempted: set[str] = set()
        self.always_inspection_failure: set[str] = set()
        self.raw_error: dict[str, Exception] = {}

    def _document(self, source_id: str, version: str, state: str) -> DocumentVersion:
        return DocumentVersion(
            SourceRef(source_id, "검증 안내", "https://example.invalid/guide", "기관", version),
            "a" * 64,
            state,  # type: ignore[arg-type]
            1,
        )

    async def inspect_version(self, source_id: str, version: str) -> PublicationInspection:
        self.inspect_calls[source_id] = self.inspect_calls.get(source_id, 0) + 1
        if source_id in self.always_inspection_failure or (
            source_id in self.outage_after_publish and source_id in self.published_attempted
        ):
            raise _connection_error()
        state = self.states.get((source_id, version))
        if state is None:
            raise PublicationError("document version has no indexed chunks")
        published_versions = tuple(
            sorted(
                candidate_version
                for (candidate_source, candidate_version), candidate_state in self.states.items()
                if candidate_source == source_id
                and candidate_version != version
                and candidate_state == "published"
            )
        )
        return PublicationInspection(self._document(source_id, version, state), published_versions)

    async def publish_with_outcome(
        self,
        source_id: str,
        version: str,
        *,
        allow_version_replacement: bool,
    ) -> PublicationOutcome:
        self.publish_calls.append((source_id, version, allow_version_replacement))
        errors = self.publish_errors.get(source_id, [])
        if errors:
            raise errors.pop(0)
        if source_id in self.raw_error:
            raise self.raw_error[source_id]
        state = self.states.get((source_id, version))
        if state == "published":
            return PublicationOutcome(
                self._document(source_id, version, state), "already_published"
            )
        if state != "indexed":
            raise PublicationError("only a complete indexed version can be published")
        old_versions = tuple(
            sorted(
                candidate_version
                for (candidate_source, candidate_version), candidate_state in self.states.items()
                if candidate_source == source_id
                and candidate_version != version
                and candidate_state == "published"
            )
        )
        if old_versions and not allow_version_replacement:
            raise ReplacementApprovalRequired("replacement approval required")
        for old_version in old_versions:
            self.states[(source_id, old_version)] = "retired"
        self.states[(source_id, version)] = "published"
        if source_id in self.outage_after_publish:
            self.published_attempted.add(source_id)
            raise _connection_error()
        if source_id in self.ambiguous_commit:
            self.ambiguous_commit.remove(source_id)
            raise _connection_error()
        return PublicationOutcome(
            self._document(source_id, version, "published"),
            "published",
            old_versions,
        )


class BatchPublicationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.result_path = Path(self.temp_dir.name) / "index-result.json"
        self.collection_id = "test-guides"

    def _write(self, payload: object) -> str:
        self.result_path.write_text(json.dumps(payload), encoding="utf-8")
        return str(self.result_path)

    def _standard(self, source_id: str, version: str, state: str = "indexed") -> dict[str, object]:
        return {
            "success": True,
            "sourceId": source_id,
            "version": version,
            "collectionId": self.collection_id,
            "state": state,
        }

    def _outcomes(
        self,
        source_versions: tuple[tuple[str, str, str], ...],
        *,
        collection_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "indexed_units": len(source_versions),
            "collection_id": collection_id or self.collection_id,
            "chunks": len(source_versions),
            "published": False,
            "outcomes": [
                {"source_id": source_id, "version": version, "indexed_state": state}
                for source_id, version, state in source_versions
            ],
        }

    def _invoke(
        self,
        payload: object,
        store: _FakePublicationStore,
        *,
        extra_args: tuple[str, ...] = (),
    ) -> tuple[int, dict[str, object] | None, str, str]:
        path = self._write(payload)
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch.object(
                rag_cli,
                "_database_for_profile",
                new_callable=AsyncMock,
                return_value=object(),
            ) as database_factory,
            patch.object(rag_cli, "_release_profile_database", new_callable=AsyncMock),
            patch.object(rag_cli, "PostgresPublicationStore", return_value=store),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = rag_cli.main(
                [
                    "publish",
                    "--from-index-result",
                    path,
                    "--collection-id",
                    self.collection_id,
                    *extra_args,
                ]
            )
        if database_factory.await_count == 0:
            summary = None
        else:
            output = stdout.getvalue().strip()
            summary = json.loads(output) if output else None
        return exit_code, summary, stdout.getvalue(), stderr.getvalue()

    def test_기존_단건_publish_인자를_그대로_전달한다(self) -> None:
        with patch.object(rag_cli, "_publish", return_value=0) as publish:
            exit_code = rag_cli.main(["publish", "--source-id", "guide-001", "--version", "sha-v1"])
        self.assertEqual(exit_code, 0)
        publish.assert_called_once_with("guide-001", "sha-v1", "published-guides")

    def test_standard_index_result를_배치_게시한다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-v1"): "indexed"})
        exit_code, summary, _, _ = self._invoke(self._standard("guide-001", "sha-v1"), store)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["publishedCount"], 1)
        self.assertEqual(summary["items"][0]["outcome"], "published")

    def test_source_v2_outcomes를_배치_게시한다(self) -> None:
        states = {("unit-01", "sha-01"): "indexed", ("unit-02", "sha-02"): "indexed"}
        store = _FakePublicationStore(states)
        payload = self._outcomes(
            (("unit-01", "sha-01", "indexed"), ("unit-02", "sha-02", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["totalCount"], 2)
        self.assertEqual(summary["publishedCount"], 2)

    def test_mapped_xlsx_outcomes를_배치_게시한다(self) -> None:
        store = _FakePublicationStore({("mapped-01", "row-sha-01"): "indexed"})
        payload = self._outcomes((("mapped-01", "row-sha-01", "indexed"),))
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["items"][0]["outcome"], "published")

    def test_이미_published인_동일_버전은_건너뛰고_재실행에_안전하다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-v1"): "published"})
        exit_code, summary, _, _ = self._invoke(
            self._standard("guide-001", "sha-v1", "published"), store
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["skippedCount"], 1)
        self.assertEqual(summary["confirmedAfterErrorCount"], 0)
        self.assertEqual(store.publish_calls, [])

    def test_다른_published_버전은_명시적_승인_없이_교체하지_않는다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-old"): "published", ("guide-001", "sha-new"): "indexed"}
        )
        exit_code, summary, _, _ = self._invoke(self._standard("guide-001", "sha-new"), store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(store.publish_calls, [])

    def test_명시적_버전_교체는_이전_버전을_retired로_전환한다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-old"): "published", ("guide-001", "sha-new"): "indexed"}
        )
        exit_code, summary, _, _ = self._invoke(
            self._standard("guide-001", "sha-new"),
            store,
            extra_args=("--allow-version-replacement",),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(store.states[("guide-001", "sha-old")], "retired")
        self.assertEqual(summary["items"][0]["retiredVersions"], ["sha-old"])

    def test_retired_버전은_재게시하지_않는다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-old"): "retired"})
        exit_code, summary, _, _ = self._invoke(self._standard("guide-001", "sha-old"), store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(store.publish_calls, [])

    def test_중복_Source_ID와_충돌_버전은_DB에_연결하기_전에_거부한다(self) -> None:
        payloads = (
            self._outcomes(
                (("guide-001", "sha-v1", "indexed"), ("guide-001", "sha-v1", "indexed"))
            ),
            self._outcomes(
                (("guide-001", "sha-v1", "indexed"), ("guide-001", "sha-v2", "indexed"))
            ),
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                store = _FakePublicationStore()
                exit_code, summary, _, stderr = self._invoke(payload, store)
                self.assertEqual(exit_code, 2)
                self.assertIsNone(summary)
                self.assertIn("source guide-001", stderr)
                self.assertEqual(store.publish_calls, [])

    def test_누락_필드와_잘린_JSON은_게시하지_않는다(self) -> None:
        store = _FakePublicationStore()
        missing = self._outcomes((("guide-001", "sha-v1", "indexed"),))
        missing["outcomes"] = [{"source_id": "guide-001", "indexed_state": "indexed"}]
        exit_code, summary, _, _ = self._invoke(missing, store)
        self.assertEqual(exit_code, 2)
        self.assertIsNone(summary)
        self.assertEqual(store.publish_calls, [])

        self.result_path.write_text('{"outcomes": [', encoding="utf-8")
        with patch.object(
            rag_cli, "_database_for_profile", new_callable=AsyncMock
        ) as database_factory:
            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = rag_cli.main(
                    [
                        "publish",
                        "--from-index-result",
                        str(self.result_path),
                        "--collection-id",
                        self.collection_id,
                    ]
                )
        self.assertEqual(exit_code, 2)
        database_factory.assert_not_awaited()
        self.assertIn("invalid JSON", stderr.getvalue())

    def test_잘못된_collection은_DB쓰기_전에_거부한다(self) -> None:
        store = _FakePublicationStore()
        payload = self._outcomes((("guide-001", "sha-v1", "indexed"),), collection_id="other")
        exit_code, summary, _, stderr = self._invoke(payload, store)
        self.assertEqual(exit_code, 2)
        self.assertIsNone(summary)
        self.assertIn("does not match", stderr)

    def test_indexed가_아닌_결과는_게시하지_않는다(self) -> None:
        store = _FakePublicationStore()
        exit_code, summary, _, _ = self._invoke(
            self._standard("guide-001", "sha-v1", "staging"), store
        )
        self.assertEqual(exit_code, 2)
        self.assertIsNone(summary)
        self.assertEqual(store.publish_calls, [])

    def test_한_Source_Unit_정책_실패는_나머지_게시를_막지_않는다(self) -> None:
        store = _FakePublicationStore(
            {("retired-guide", "sha-old"): "retired", ("valid-guide", "sha-v1"): "indexed"}
        )
        payload = self._outcomes(
            (("retired-guide", "sha-old", "indexed"), ("valid-guide", "sha-v1", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["publishedCount"], 1)
        self.assertEqual(store.states[("valid-guide", "sha-v1")], "published")

    def test_일시적_DB_오류는_새_트랜잭션으로_한번_재시도한다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-v1"): "indexed"})
        store.publish_errors["guide-001"] = [_sqlstate_error("40001")]
        exit_code, summary, _, _ = self._invoke(self._standard("guide-001", "sha-v1"), store)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["publishedCount"], 1)
        self.assertEqual(len(store.publish_calls), 2)

    def test_커밋_결과가_불명확하면_confirmed_after_error로_분류하고_배치를_중단한다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-v1"): "indexed", ("guide-002", "sha-v2"): "indexed"}
        )
        store.ambiguous_commit.add("guide-001")
        payload = self._outcomes(
            (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["publishedCount"], 0)
        self.assertEqual(summary["skippedCount"], 0)
        self.assertEqual(summary["confirmedAfterErrorCount"], 1)
        self.assertEqual(summary["notAttemptedCount"], 1)
        self.assertEqual(summary["items"][0]["outcome"], "confirmed_after_error")
        self.assertEqual(summary["items"][1]["outcome"], "not_attempted")
        self.assertEqual(len(store.publish_calls), 1)

    def test_서버_종료와_08_연결오류는_상태를_확인하고_남은_항목을_중단한다(self) -> None:
        for sqlstate in ("57P01", "57P02", "57P03", "08006"):
            with self.subTest(sqlstate=sqlstate):
                store = _FakePublicationStore(
                    {
                        ("guide-001", "sha-v1"): "indexed",
                        ("guide-002", "sha-v2"): "indexed",
                    }
                )
                store.publish_errors["guide-001"] = [_sqlstate_error(sqlstate)]
                payload = self._outcomes(
                    (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
                )
                exit_code, summary, _, _ = self._invoke(payload, store)
                self.assertEqual(exit_code, 1)
                self.assertEqual(summary["failedCount"], 1)
                self.assertEqual(summary["notAttemptedCount"], 1)
                self.assertEqual(summary["databaseUnavailableCount"], 1)
                self.assertEqual(summary["items"][0]["publicationState"], "indexed")
                self.assertEqual(summary["items"][0]["sqlstate"], sqlstate)
                self.assertEqual(summary["items"][1]["outcome"], "not_attempted")
                self.assertEqual(len(store.publish_calls), 1)

    def test_드라이버_예외에_감긴_SQLSTATE를_추출한다(self) -> None:
        error = _sqlstate_error("57P03", nested=True)
        self.assertEqual(rag_cli._sqlstate(error), "57P03")
        self.assertTrue(rag_cli._is_database_wide_error(error))

    def test_일반_항목_오류는_다음_Source_Unit을_계속_처리한다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-v1"): "indexed", ("guide-002", "sha-v2"): "indexed"}
        )
        store.raw_error["guide-001"] = RuntimeError("item policy failure")
        payload = self._outcomes(
            (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["publishedCount"], 1)
        self.assertEqual(store.states[("guide-002", "sha-v2")], "published")

    def test_사전검증_중_전체_DB_장애면_게시를_시작하지_않는다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-v1"): "indexed", ("guide-002", "sha-v2"): "indexed"}
        )
        store.always_inspection_failure.add("guide-001")
        payload = self._outcomes(
            (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["notAttemptedCount"], 1)
        self.assertEqual(store.publish_calls, [])

    def test_게시_중_DB가_중단되면_남은_항목을_not_attempted로_남긴다(self) -> None:
        store = _FakePublicationStore(
            {("guide-001", "sha-v1"): "indexed", ("guide-002", "sha-v2"): "indexed"}
        )
        store.outage_after_publish.add("guide-001")
        payload = self._outcomes(
            (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
        )
        exit_code, summary, _, _ = self._invoke(payload, store)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["notAttemptedCount"], 1)
        self.assertEqual(summary["databaseUnavailableCount"], 1)
        self.assertEqual(summary["items"][0]["publicationState"], "unknown")
        self.assertEqual(store.states[("guide-002", "sha-v2")], "indexed")

    def test_DB_오류에_포함된_연결정보를_출력하지_않는다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-v1"): "indexed"})
        store.raw_error["guide-001"] = RuntimeError(
            "postgresql://rag-user:secret@db.example.invalid/rag"
        )
        exit_code, summary, stdout, stderr = self._invoke(
            self._standard("guide-001", "sha-v1"), store
        )
        self.assertEqual(exit_code, 1)
        self.assertNotIn("secret", stdout + stderr)
        self.assertIn("RuntimeError", stdout)
        self.assertEqual(summary["failedCount"], 1)

    def test_DB_전체장애_결과_JSON도_인증정보를_마스킹한다(self) -> None:
        store = _FakePublicationStore({("guide-001", "sha-v1"): "indexed"})
        store.publish_errors["guide-001"] = [
            _sqlstate_error("57P01", detail="postgresql://user:secret@host/db")
        ]
        exit_code, summary, stdout, stderr = self._invoke(
            self._standard("guide-001", "sha-v1"), store
        )
        self.assertEqual(exit_code, 1)
        self.assertNotIn("secret", stdout + stderr + json.dumps(summary))
        self.assertEqual(summary["items"][0]["errorType"], "DBAPIError")
        self.assertEqual(summary["items"][0]["sqlstate"], "57P01")

    def test_DB_접속_초기화_장애는_모든_항목을_not_attempted로_기록한다(self) -> None:
        payload = self._outcomes(
            (("guide-001", "sha-v1", "indexed"), ("guide-002", "sha-v2", "indexed"))
        )
        path = self._write(payload)
        stdout = StringIO()
        stderr = StringIO()
        connection_error = _sqlstate_error("57P03", detail="postgresql://user:secret@host/db")
        with (
            patch.object(
                rag_cli,
                "_database_for_profile",
                new_callable=AsyncMock,
                side_effect=connection_error,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = rag_cli.main(
                ["publish", "--from-index-result", path, "--collection-id", self.collection_id]
            )
        summary = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["notAttemptedCount"], 2)
        self.assertEqual(summary["databaseUnavailableCount"], 1)
        self.assertEqual(summary["databaseUnavailable"], True)
        self.assertEqual(summary["sqlstate"], "57P03")
        self.assertNotIn("secret", stdout.getvalue() + stderr.getvalue())

    def test_batch와_단건_옵션을_혼용하지_못한다(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            rag_cli.main(
                [
                    "publish",
                    "--from-index-result",
                    "index.json",
                    "--source-id",
                    "guide-001",
                    "--version",
                    "sha-v1",
                ]
            )
        self.assertEqual(raised.exception.code, 2)


class _FixedEmbedding:
    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (0.01,) * 768

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((0.01,) * 768 for _ in texts)


class PublicationStoreOutcomeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_url = os.environ.get("RAG_DATABASE_URL", "").strip()
        if not raw_url:
            raise unittest.SkipTest("RAG_DATABASE_URL is not set; local pgvector check was not run")
        try:
            cls.database_url = rag_cli.database_url_from_environment()
        except DatabaseConfigurationError as error:
            raise unittest.SkipTest(
                "RAG_DATABASE_URL does not target the approved local test DB"
            ) from error

    def test_publication_outcome_reuse_replacement_and_retired_rejection(self) -> None:
        async def run() -> None:
            database = PostgresRagDatabase(self.database_url)
            collection_id = f"rag-test-publication-{uuid.uuid4().hex[:12]}"
            vector_store = PGVectorStore(database, _FixedEmbedding(), collection_id=collection_id)
            publication_store = PostgresPublicationStore(database, collection_id=collection_id)

            async def index_version(source_id: str, version: str) -> None:
                source = SourceRef(
                    source_id,
                    "[합성 시험 자료] 게시 테스트",
                    "https://example.invalid/publication-test",
                    "게시 테스트",
                    version,
                )
                chunk = ChunkRecord(
                    f"{source_id}:{version}:chunk-1",
                    source_id,
                    version,
                    f"publication test content {version}",
                    '{"status":"verified","page_numbers":[1]}',
                )
                document = DocumentVersion(source, "b" * 64, "staging", 1)
                await vector_store.index_document(document, (chunk,), is_synthetic=True)

            try:
                await database.initialize()
                await index_version("batch-outcome", "sha-old")
                first = await publication_store.publish_with_outcome(
                    "batch-outcome", "sha-old", allow_version_replacement=True
                )
                repeated = await publication_store.publish_with_outcome(
                    "batch-outcome", "sha-old", allow_version_replacement=False
                )
                self.assertEqual(first.disposition, "published")
                self.assertEqual(repeated.disposition, "already_published")

                await index_version("batch-outcome", "sha-new")
                inspection = await publication_store.inspect_version("batch-outcome", "sha-new")
                self.assertEqual(inspection.document.state, "indexed")
                self.assertEqual(inspection.published_versions, ("sha-old",))
                with self.assertRaises(ReplacementApprovalRequired):
                    await publication_store.publish_with_outcome(
                        "batch-outcome", "sha-new", allow_version_replacement=False
                    )
                replaced = await publication_store.publish_with_outcome(
                    "batch-outcome", "sha-new", allow_version_replacement=True
                )
                self.assertEqual(replaced.disposition, "published")
                self.assertEqual(replaced.retired_versions, ("sha-old",))
                with self.assertRaises(PublicationError):
                    await publication_store.publish_with_outcome(
                        "batch-outcome", "sha-old", allow_version_replacement=True
                    )
            finally:
                await database.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
