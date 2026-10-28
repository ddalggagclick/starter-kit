from __future__ import annotations

import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from threading import Event
from unittest.mock import patch

from starter_rag.progress import run_with_heartbeat


class ProgressHeartbeatTests(unittest.TestCase):
    def test_알수없는_진행률은_단계와_경과시간만_표시한다(self):
        reported = Event()

        class HeartbeatOutput(StringIO):
            def write(self, text):
                result = super().write(text)
                if "경과" in text:
                    reported.set()
                return result

        output = HeartbeatOutput()

        def operation():
            if not reported.wait(timeout=2):
                raise TimeoutError("진행 알림이 발생하지 않았습니다.")
            return "done"

        with patch.dict(os.environ, {"RAG_PROGRESS": "1"}, clear=True), redirect_stderr(output):
            result = run_with_heartbeat(
                operation,
                "PDF 파싱",
                interval_seconds=0.001,
            )

        self.assertEqual(result, "done")
        self.assertIn("PDF 파싱 중", output.getvalue())
        self.assertIn("경과 (진행률 미확인)", output.getvalue())
        self.assertNotIn("%", output.getvalue())

    def test_작업_오류를_전달하고_진행_알림을_종료한다(self):
        output = StringIO()
        with (
            patch.dict(os.environ, {"RAG_PROGRESS": "1"}, clear=True),
            redirect_stderr(output),
            self.assertRaisesRegex(RuntimeError, "operation failed"),
        ):
            run_with_heartbeat(
                lambda: (_ for _ in ()).throw(RuntimeError("operation failed")),
                "청킹",
                interval_seconds=3600,
            )

        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
