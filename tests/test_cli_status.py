"""CLI status reports implementation and configuration without probing services."""

from __future__ import annotations

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from starter_rag import cli as rag_cli


class CliStatusTests(unittest.TestCase):
    def _run_status(self, database_url: str | None) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        environment = {} if database_url is None else {"RAG_DATABASE_URL": database_url}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                rag_cli,
                "_database_for_command",
                side_effect=AssertionError("status must not connect to the database"),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = rag_cli.main(["status"])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_missing_database_configuration_still_reports_implemented_offline_status(self) -> None:
        result, stdout, stderr = self._run_status(None)

        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {
                "package": "starter-rag",
                "status": "implemented",
                "searchImplemented": True,
                "ingestionImplemented": True,
                "databaseConfigured": False,
                "runtimeReadiness": "not-checked",
            },
        )

    def test_valid_local_database_configuration_does_not_claim_runtime_ready(self) -> None:
        result, stdout, stderr = self._run_status(
            "postgresql+asyncpg://rag@/starter_rag_integration?host=%2Ftmp"
        )

        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["databaseConfigured"])
        self.assertEqual(payload["runtimeReadiness"], "not-checked")
        self.assertNotEqual(payload["status"], "ready")

    def test_rejected_remote_database_url_does_not_fail_or_echo_secrets(self) -> None:
        result, stdout, stderr = self._run_status(
            "postgresql+asyncpg://user:status-secret@db.supabase.co:5432/postgres"
        )

        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertFalse(payload["databaseConfigured"])
        self.assertEqual(payload["runtimeReadiness"], "not-checked")
        self.assertNotIn("status-secret", stdout)


if __name__ == "__main__":
    unittest.main()
