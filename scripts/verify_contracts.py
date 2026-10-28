# 담당: [통합] | 책임: 공개 계약과 저장소 구조의 정적 검증.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (계약 검증 지원)
# 구현할 기능: Python AST, JSON 형식, 내부 패키지 의존 방향을 검사한다.
# 완료 기준: AST·JSON·의존 경계 위반이 있으면 종료 코드 1을 반환한다.
# 제한사항: 정적 검증 통과는 UI·DB·LLM 실연동 검증을 뜻하지 않는다.
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
GENERATED_DIRS = {
    ".venv",
    "node_modules",
    "dist",
    ".git",
    ".vite",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
}

CHECKED_SUFFIXES = {".py", ".json"}


def check_file(p: Path) -> None:
    rel = p.relative_to(ROOT).as_posix()
    if p.suffix == ".py":
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except UnicodeError as exc:
            ERRORS.append(f"{rel}: unsupported source encoding ({exc})")
            return
        except SyntaxError as exc:
            ERRORS.append(f"{rel}: SyntaxError {exc}")
            return
        if rel.startswith(("rag/", "llm/")):
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    names = [alias.name for alias in n.names]
                elif isinstance(n, ast.ImportFrom):
                    names = [n.module or ""]
                else:
                    continue
                if any(z == "inheritance" or z.startswith("inheritance.") for z in names):
                    ERRORS.append(f"{rel}: forbidden dependency to inheritance")
                if rel.startswith("rag/") and any(
                    z == "starter_llm" or z.startswith("starter_llm.") for z in names
                ):
                    ERRORS.append(f"{rel}: rag imports starter_llm")
                if rel.startswith("llm/") and any(
                    z == "starter_rag" or z.startswith("starter_rag.") for z in names
                ):
                    ERRORS.append(f"{rel}: llm imports starter_rag")
    if p.suffix == ".json":
        try:
            raw = p.read_text(encoding="utf-8")
            if rel.startswith("frontend/tsconfig"):
                raw = "\n".join(
                    line for line in raw.splitlines() if not line.lstrip().startswith("//")
                )
            json.loads(raw)
        except UnicodeError as exc:
            ERRORS.append(f"{rel}: unsupported source encoding ({exc})")
        except json.JSONDecodeError as exc:
            ERRORS.append(f"{rel}: JSON {exc}")
    # shadcn CLI owns this strict JSON config; validate the keys used by the frontend.
    if rel == "frontend/components.json":
        d = json.loads(p.read_text(encoding="utf-8"))
        if (
            not all(k in d for k in ("$schema", "tailwind", "aliases"))
            or d["aliases"].get("ui") != "@/components/ui"
        ):
            ERRORS.append(f"{rel}: invalid shadcn CLI configuration")


def main() -> int:
    count = 0
    tracked_and_unignored = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    for relative_path in tracked_and_unignored.split(b"\0"):
        if not relative_path:
            continue
        p = ROOT / os.fsdecode(relative_path)
        if (
            not p.is_file()
            or p.suffix not in CHECKED_SUFFIXES
            or any(part in GENERATED_DIRS for part in p.relative_to(ROOT).parts)
        ):
            continue
        count += 1
        check_file(p)
    for err in ERRORS:
        print("FAIL", err)
    print(f"Contract file checks: {count} files; problems={len(ERRORS)}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
