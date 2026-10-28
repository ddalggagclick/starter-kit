# 책임: [통합] 최소 실행 진입점 회귀 검사.
# 구현할 기능: FastAPI health/CORS와 LLM·RAG CLI 계약 확인.
# 완료 기준: python -m unittest discover -s tests -v 통과.
import contextlib
import unittest
from io import StringIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from inheritance.main import app
from starter_llm.cli import main as llm_main
from starter_rag.cli import main as rag_main


class EntrypointTests(unittest.TestCase):
    def test_health(self):
        with TestClient(app) as client:
            result = client.get("/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "ok")

    def test_cors(self):
        with TestClient(app) as client:
            good = client.options(
                "/health",
                headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
            )
            bad = client.options(
                "/health",
                headers={"Origin": "https://evil.invalid", "Access-Control-Request-Method": "GET"},
            )
        self.assertEqual(good.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertNotIn("access-control-allow-origin", bad.headers)

    def test_llm_cli(self):
        out = StringIO()
        with contextlib.redirect_stdout(out):
            code = llm_main(["validate", "--prompt", "테스트"])
        self.assertEqual(code, 0)
        self.assertIn('"valid": true', out.getvalue())

    def test_검색어_위치_인자를_검증한다(self):
        out = StringIO()
        with (
            patch("starter_rag.cli._search", return_value=0) as search,
            contextlib.redirect_stdout(out),
        ):
            code = rag_main(["search", "상속 포기"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        search.assert_called_once_with("상속 포기", 3, "published-guides", False)
