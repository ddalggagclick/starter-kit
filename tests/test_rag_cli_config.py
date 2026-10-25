"""Local CLI settings persist privately while environment values take precedence."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from starter_rag import cli
from starter_rag.local_config import (
    ConfigError,
    display_config,
    effective_config,
    save_config_from_environment,
    validate_config,
)


class RagCliConfigTests(unittest.TestCase):
    def test_설정_저장과_조회에서_데이터베이스_비밀번호를_가린다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            values = {
                "RAG_CONFIG_PATH": str(path),
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester:secret@127.0.0.1/rag_isolated_test",
                "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
            }
            with (
                patch.dict("os.environ", values, clear=True),
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(cli.main(["config", "setup"]), 0)
                self.assertNotIn("secret", output.getvalue())
            with (
                patch.dict("os.environ", {"RAG_CONFIG_PATH": str(path)}, clear=True),
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(cli.main(["config", "show"]), 0)
                self.assertNotIn("secret", output.getvalue())
                self.assertEqual(cli.main(["status"]), 0)
                self.assertTrue(
                    json.loads(output.getvalue().splitlines()[-1])["databaseConfigured"]
                )
            with (
                patch.dict(
                    "os.environ",
                    {"RAG_CONFIG_PATH": str(path), "RAG_CHUNKING_MODEL": "override"},
                    clear=True,
                ),
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(cli.main(["config", "show"]), 0)
                self.assertEqual(
                    json.loads(output.getvalue())["settings"]["RAG_CHUNKING_MODEL"], "override"
                )

    def test_잘못된_연결문자열을_비밀값_없이_진단한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = {
                "RAG_CONFIG_PATH": str(Path(directory) / "missing.json"),
                "RAG_DATABASE_URL": "postgresql+asyncpg://u:secret@remote.example.com/db",
            }
            with patch.dict("os.environ", values, clear=True), redirect_stderr(StringIO()) as error:
                self.assertEqual(cli.main(["config", "validate"]), 2)
                self.assertNotIn("secret", error.getvalue())

    def test_설정을_재사용하고_개인_파일_권한을_적용한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            env = {
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester:secret@127.0.0.1/rag_isolated_test",
                "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
                "RAG_TOKENIZER_PATH": "/local/tokenizer",
                "RAG_CHUNKING_PROVIDER": "ollama",
                "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
            }
            save_config_from_environment(path, env)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                json.loads(path.read_text())["RAG_CHUNKING_MODEL"], "qwen3:4b-instruct"
            )
            self.assertEqual(
                effective_config(path, {})["RAG_DATABASE_URL"], env["RAG_DATABASE_URL"]
            )
            self.assertEqual(
                effective_config(path, {"RAG_CHUNKING_MODEL": "override"})["RAG_CHUNKING_MODEL"],
                "override",
            )
            self.assertNotIn("secret", json.dumps(display_config(effective_config(path, {}))))

    def test_잘못됐거나_원격인_로컬_데이터베이스를_거부한다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with self.assertRaises(ConfigError):
                save_config_from_environment(
                    path, {"RAG_DATABASE_URL": "postgresql+asyncpg://u@remote.example.com/db"}
                )
            self.assertFalse(path.exists())
            with self.assertRaises(ConfigError):
                validate_config(
                    {
                        "RAG_DATABASE_URL": "postgresql+asyncpg://u@127.0.0.1/postgres",
                        "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
                    }
                )

    def test_검색_후보설정은_열개를_넘길_수_없다(self) -> None:
        with self.assertRaises(ConfigError):
            validate_config(
                {
                    "RAG_DATABASE_URL": "postgresql+asyncpg://tester@127.0.0.1/rag_isolated_test",
                    "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
                    "RAG_SEARCH_CANDIDATE_COUNT": "11",
                }
            )

        with (
            patch.dict("os.environ", {"RAG_SEARCH_CANDIDATE_COUNT": "30"}, clear=True),
            redirect_stderr(StringIO()) as error,
        ):
            self.assertEqual(cli.main(["search", "generic query"]), 2)
        self.assertIn("1~10", error.getvalue())
