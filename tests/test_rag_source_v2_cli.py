"""기존 starter-rag CLI에서 Source_v2 검증과 적재 진입점을 확인한다."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import ANY, AsyncMock, patch

from rag_test_fixtures import environment_with_home
from starter_rag import cli as rag_cli


class SourceV2CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source_path = Path(self.temp_dir.name) / "Source_v2.xlsx"
        self.source_path.touch()
        self.rag_config_path = Path(self.temp_dir.name) / "config.json"
        config_environment = patch.dict(
            "os.environ", {"RAG_CONFIG_PATH": str(self.rag_config_path)}
        )
        config_environment.start()
        self.addCleanup(config_environment.stop)

    def _isolated_environment(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        values = {"RAG_CONFIG_PATH": str(self.rag_config_path)}
        values.update(overrides or {})
        return environment_with_home(values)

    def test_검증명령은계약정보를출력한다(self) -> None:
        stdout = StringIO()
        expected = {"approved": 31, "source_units": ["내부 전용"]}

        with (
            patch.object(rag_cli, "inspect_source_v2", return_value=expected.copy()) as inspect,
            redirect_stdout(stdout),
        ):
            exit_code = rag_cli.main(["check", str(self.source_path)])

        self.assertEqual(exit_code, 0)
        inspect.assert_called_once_with(str(self.source_path))
        self.assertEqual(json.loads(stdout.getvalue()), {"approved": 31, "db_write": False})

    def test_잘못된원본파일은입력오류코드로종료한다(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr):
            exit_code = rag_cli.main(["check", str(self.source_path)])

        self.assertEqual(exit_code, 2)
        self.assertIn("Source_v2", stderr.getvalue())

    def test_행검증은데이터베이스쓰기없이실제행검증서비스를호출한다(self) -> None:
        stdout = StringIO()
        units = tuple(object() for _ in range(31))
        rows = {str(index): object() for index in range(31)}

        with (
            patch.object(
                rag_cli,
                "inspect_source_v2",
                return_value={"approved": 31, "source_units": ["내부 전용"]},
            ) as inspect,
            patch.object(
                rag_cli,
                "verify_source_rows",
                new_callable=AsyncMock,
                return_value=(units, rows),
            ) as verify,
            patch.object(rag_cli, "_load_tokenizer", return_value=object()),
            patch.object(
                rag_cli,
                "_database_for_command",
                side_effect=AssertionError("검증 명령은 DB를 사용하면 안 된다"),
            ),
            redirect_stdout(stdout),
        ):
            exit_code = rag_cli.main(
                [
                    "check",
                    str(self.source_path),
                    "--rows",
                    "--tokenizer-path",
                    "/local/tokenizer",
                ]
            )

        self.assertEqual(exit_code, 0)
        inspect.assert_called_once_with(str(self.source_path))
        verify.assert_awaited_once_with(str(self.source_path), count_tokens=ANY)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "approved": 31,
                "db_write": False,
                "verified_units": 31,
                "verified_table_rows": 31,
                "chunk_kind": "table_row",
                "generation_method": "deterministic",
                "model_calls_for_table_rows": 0,
            },
        )

    def test_색인은명시적으로격리컬렉션에실행한다(self) -> None:
        stdout = StringIO()
        expected = {"indexed_units": 31, "collection_id": "source-v2-e2e"}

        with (
            patch.object(
                rag_cli,
                "index_source_v2",
                new_callable=AsyncMock,
                return_value=expected,
            ) as index,
            patch.object(rag_cli, "_load_tokenizer", return_value=object()),
            redirect_stdout(stdout),
        ):
            exit_code = rag_cli.main(
                [
                    "index",
                    str(self.source_path),
                    "--type",
                    "source-v2",
                    "--tokenizer-path",
                    "/local/tokenizer",
                    "--collection-id",
                    "source-v2-e2e",
                ]
            )

        self.assertEqual(exit_code, 0)
        index.assert_awaited_once_with(
            str(self.source_path),
            count_tokens=ANY,
            collection_id="source-v2-e2e",
        )
        self.assertEqual(json.loads(stdout.getvalue()), expected)

    def test_소스_v2_색인은_환경_토크나이저와_기본_격리_컬렉션을_사용한다(self) -> None:
        environment = {"RAG_TOKENIZER_PATH": "/env/tokenizer"}
        with (
            patch.dict("os.environ", self._isolated_environment(environment), clear=True),
            patch.object(rag_cli, "_load_tokenizer", return_value=object()) as load_tokenizer,
            patch.object(
                rag_cli,
                "index_source_v2",
                new_callable=AsyncMock,
                return_value={"indexed_units": 31, "published": False},
            ) as index,
            patch.object(rag_cli, "_publish") as publish,
            redirect_stdout(StringIO()),
        ):
            exit_code = rag_cli.main(["index", str(self.source_path), "--type", "source-v2"])

        self.assertEqual(exit_code, 0)
        load_tokenizer.assert_called_once_with("/env/tokenizer")
        index.assert_awaited_once_with(
            str(self.source_path),
            count_tokens=ANY,
            collection_id="rag-test-source-v2-e2e",
        )
        publish.assert_not_called()

    def test_일반_색인은_필수_출처_메타데이터와_기본_컬렉션을_검증한다(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            rag_cli.main(["index", str(self.source_path)])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--source-id", stderr.getvalue())
        self.assertIn("--publisher", stderr.getvalue())

    def test_일반_색인은_URL없이_색인만_수행한다(self) -> None:
        environment = {"RAG_TOKENIZER_PATH": "/env/tokenizer"}
        with (
            patch.dict("os.environ", self._isolated_environment(environment), clear=True),
            patch.object(rag_cli, "_index_file", return_value=0) as index,
            patch.object(rag_cli, "_publish") as publish,
        ):
            exit_code = rag_cli.main(
                [
                    "index",
                    str(self.source_path),
                    "--source-id",
                    "guide-001",
                    "--version",
                    "1.0",
                    "--source-title",
                    "사용 설명서",
                    "--publisher",
                    "Example",
                ]
            )

        self.assertEqual(exit_code, 0)
        index.assert_called_once_with(
            str(self.source_path),
            tokenizer_path="/env/tokenizer",
            source_id="guide-001",
            version="1.0",
            source_title="사용 설명서",
            source_url=None,
            publisher="Example",
            collection_id="published-guides",
            target_tokens=512,
            is_synthetic=False,
        )
        publish.assert_not_called()

    def test_합성_색인은_별도_collection과_표시된_제목을_요구한다(self) -> None:
        with patch.dict(
            "os.environ",
            self._isolated_environment({"RAG_TOKENIZER_PATH": "/env/tokenizer"}),
            clear=True,
        ):
            stderr = StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                rag_cli.main(
                    [
                        "index",
                        str(self.source_path),
                        "--source-id",
                        "synthetic-001",
                        "--version",
                        "1.0",
                        "--source-title",
                        "[합성 시험 자료] 안내",
                        "--publisher",
                        "테스트",
                        "--synthetic",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("별도 collection", stderr.getvalue())

    def test_필수옵션없는색인은사용법오류를반환한다(self) -> None:
        stderr = StringIO()

        with (
            patch.dict("os.environ", self._isolated_environment(), clear=True),
            redirect_stderr(stderr),
        ):
            exit_code = rag_cli.main(["index", str(self.source_path), "--type", "source-v2"])

        self.assertEqual(exit_code, 2)
        self.assertIn("--tokenizer-path", stderr.getvalue())

    def test_색인실패는민감정보를출력하지않고실패코드를반환한다(self) -> None:
        stderr = StringIO()

        with (
            patch.object(
                rag_cli,
                "index_source_v2",
                new_callable=AsyncMock,
                side_effect=RuntimeError("postgresql://user:secret@localhost/db"),
            ),
            patch.object(rag_cli, "_load_tokenizer", return_value=object()),
            redirect_stderr(stderr),
        ):
            exit_code = rag_cli.main(
                [
                    "index",
                    str(self.source_path),
                    "--type",
                    "source-v2",
                    "--tokenizer-path",
                    "/local/tokenizer",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("RuntimeError", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())

    def test_평가명령에데이터셋과검색모드를전달한다(self) -> None:
        with patch.object(rag_cli, "evaluate_source_v2_golden", return_value=0) as evaluate:
            exit_code = rag_cli.main(
                [
                    "test",
                    "--dataset",
                    "/local/golden.json",
                    "--mode",
                    "title",
                    "--group",
                    "partial",
                    "--out",
                    "/tmp/result.json",
                    "--validate-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        evaluate.assert_called_once_with(
            dataset_path=Path("/local/golden.json"),
            mode="title",
            group="partial",
            out_path=Path("/tmp/result.json"),
            validate_only=True,
        )

    def test_기본평가자료에서26문항과38개근거라벨을검증한다(self) -> None:
        stdout = StringIO()

        with (
            patch(
                "starter_rag.evaluation.golden_set._search_source_v2_golden",
                side_effect=AssertionError("검증 전용 평가는 검색을 실행하면 안 된다"),
            ),
            redirect_stdout(stdout),
        ):
            exit_code = rag_cli.main(["test", "--validate-only"])

        self.assertEqual(exit_code, 0)
        self.assertIn("26 questions; 38 verified evidence labels", stdout.getvalue())

    def test_없는_평가자료는_입력_오류_코드로_종료한다(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            exit_code = rag_cli.main(["test", "--dataset", "/missing/golden.json"])

        self.assertEqual(exit_code, 2)
        self.assertIn("FileNotFoundError", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
