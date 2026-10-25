# 담당: [D] | 책임: CLI 작업의 비밀정보 없는 진행 상태를 출력한다.
# 구현할 기능: 알 수 없는 진행률은 단계와 경과 시간만 stderr에 표시한다.
# 완료 기준: 작업 결과와 예외를 보존하고 백분율을 만들지 않는다.
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from threading import Event, Thread
from time import monotonic


def run_with_heartbeat[ResultT](
    operation: Callable[[], ResultT],
    stage: str,
    *,
    interval_seconds: float = 20.0,
    enabled: bool | None = None,
) -> ResultT:
    """Run a blocking operation and report elapsed time when progress is unknown."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    should_report = (
        os.environ.get("RAG_PROGRESS") == "1" or sys.stderr.isatty() if enabled is None else enabled
    )
    if not should_report:
        return operation()

    stop = Event()

    def report() -> None:
        started_at = monotonic()
        while not stop.wait(interval_seconds):
            elapsed = int(monotonic() - started_at)
            minutes, seconds = divmod(elapsed, 60)
            print(
                f"{stage} 중 · {minutes}분 {seconds}초 경과 (진행률 미확인)",
                file=sys.stderr,
                flush=True,
            )

    reporter = Thread(target=report, name="rag-progress-heartbeat", daemon=True)
    reporter.start()
    try:
        return operation()
    finally:
        stop.set()
        reporter.join()
