"""Local CLI settings persist privately while environment values take precedence."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rag_test_fixtures import environment_with_home
from starter_rag import cli, local_config
from starter_rag.local_config import (
    ConfigError,
    config_path,
    display_config,
    effective_config,
    save_config_from_environment,
    validate_config,
)


class RagCliConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.rag_config_path = Path(self.temp_dir.name) / "config.json"

    def _isolated_environment(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        values = {"RAG_CONFIG_PATH": str(self.rag_config_path)}
        values.update(overrides or {})
        return environment_with_home(values)

    def test_명시적_설정_경로는_홈_경로를_조회하지_않는다(self) -> None:
        with patch.object(Path, "home", side_effect=AssertionError("Path.home() 호출됨")):
            self.assertEqual(
                config_path({"RAG_CONFIG_PATH": str(self.rag_config_path)}),
                self.rag_config_path,
            )
            self.assertEqual(
                config_path({"RAG_CONFIG_PATH": "relative/rag-config.json"}),
                Path("relative/rag-config.json"),
            )

    def test_기본_경로와_사용자_홈_확장을_유지한다(self) -> None:
        home = Path(self.temp_dir.name)
        home_values = environment_with_home(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "HOMEDRIVE": home.drive,
                "HOMEPATH": str(home)[len(home.drive) :],
            },
            environ={},
        )
        with patch.dict(os.environ, home_values, clear=True):
            with patch.object(Path, "home", return_value=home) as home_lookup:
                self.assertEqual(
                    config_path({}),
                    home / ".config" / "starter-rag" / "config.json",
                )
                home_lookup.assert_called_once_with()

            with patch.object(Path, "home", side_effect=AssertionError("Path.home() 호출됨")):
                self.assertEqual(
                    config_path({"RAG_CONFIG_PATH": "~/rag-config.json"}),
                    home / "rag-config.json",
                )

    def test_격리_환경은_최소한의_홈_경로변수만_보존한다(self) -> None:
        original = {
            "HOME": "/home/tester",
            "USERPROFILE": r"C:\Users\tester",
            "HOMEDRIVE": "C:",
            "HOMEPATH": r"\Users\tester",
            "DATABASE_URL": "must-not-be-preserved",
        }

        environment = environment_with_home(
            {"RAG_CONFIG_PATH": "C:/tmp/rag-config.json"}, environ=original
        )

        self.assertEqual(
            environment,
            {
                "HOME": "/home/tester",
                "USERPROFILE": r"C:\Users\tester",
                "HOMEDRIVE": "C:",
                "HOMEPATH": r"\Users\tester",
                "RAG_CONFIG_PATH": "C:/tmp/rag-config.json",
            },
        )

    def test_설정_저장과_조회에서_데이터베이스_비밀번호를_가린다(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            values = {
                "RAG_CONFIG_PATH": str(path),
                "RAG_DATABASE_URL": "postgresql+asyncpg://tester:secret@127.0.0.1/rag_isolated_test",
                "RAG_LOCAL_DATABASE_NAME": "rag_isolated_test",
            }
            with (
                patch.dict("os.environ", environment_with_home(values), clear=True),
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(cli.main(["config", "setup"]), 0)
                self.assertNotIn("secret", output.getvalue())
            with (
                patch.dict(
                    "os.environ",
                    environment_with_home({"RAG_CONFIG_PATH": str(path)}),
                    clear=True,
                ),
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
                    environment_with_home(
                        {"RAG_CONFIG_PATH": str(path), "RAG_CHUNKING_MODEL": "override"}
                    ),
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
            with (
                patch.dict("os.environ", environment_with_home(values), clear=True),
                redirect_stderr(StringIO()) as error,
            ):
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
            if os.name == "posix":
                # Windows chmod exposes a read-only flag, not POSIX permission bits.
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["RAG_CHUNKING_MODEL"],
                "qwen3:4b-instruct",
            )
            self.assertEqual(
                effective_config(path, {})["RAG_DATABASE_URL"], env["RAG_DATABASE_URL"]
            )

            if os.name == "posix":
                path.chmod(0o644)
            # Branch simulation only; this does not inspect or prove Windows ACL protection.
            with patch.object(local_config, "os", SimpleNamespace(name="nt")):
                saved = effective_config(path, {})
                overridden = effective_config(path, {"RAG_CHUNKING_MODEL": "override"})
            self.assertEqual(saved["RAG_CHUNKING_MODEL"], "qwen3:4b-instruct")
            self.assertEqual(overridden["RAG_CHUNKING_MODEL"], "override")
            self.assertNotIn("secret", json.dumps(display_config(saved)))

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
            patch.dict(
                "os.environ",
                self._isolated_environment({"RAG_SEARCH_CANDIDATE_COUNT": "30"}),
                clear=True,
            ),
            redirect_stderr(StringIO()) as error,
        ):
            self.assertEqual(cli.main(["search", "generic query"]), 2)
        self.assertIn("1~10", error.getvalue())
