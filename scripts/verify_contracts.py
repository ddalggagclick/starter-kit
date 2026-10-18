# 담당: [통합] | 책임: 공개 계약과 저장소 구조의 정적 검증.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-1 (계약 검증 지원)
# 구현할 기능: Work Order 주석, Python AST, JSON 형식, 내부 패키지 의존 방향을 검사한다.
# 완료 기준: 검사 위반이 있으면 종료 코드 1을 반환한다.
# 제한사항: 정적 검증 통과는 UI·DB·LLM 실연동 검증을 뜻하지 않는다.
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
IGNORE = {".python-version", ".node-version"}
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

# 검사 대상은 실제 소스/설정/문서다. 다운로드 바이너리·.DS_Store는 읽지 않는다.
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".jsonc",
    ".toml",
    ".yml",
    ".yaml",
    ".ini",
    ".css",
    ".html",
    ".sh",
    ".sql",
    ".svg",
    ".txt",
    ".example",
    ".development",
    ".gitignore",
}
TEXT_FILENAMES = {".gitignore", ".env", "Dockerfile", "Makefile"}


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
    # shadcn CLI owns a strict JSON config: comments/custom metadata would break CLI compatibility.
    # Validate essential CLI schema keys instead of requiring human-readable header comments.
    if rel == "frontend/components.json":
        d = json.loads(p.read_text(encoding="utf-8"))
        if (
            not all(k in d for k in ("$schema", "tailwind", "aliases"))
            or d["aliases"].get("ui") != "@/components/ui"
        ):
            ERRORS.append(f"{rel}: invalid shadcn CLI configuration")
        return
    # These files use rigid third-party formats; do not demand Work Order comments.
    if rel in {
        "frontend/package-lock.json",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/issue-template.md",
    }:
        return
    # Readability: ownership comments in source/docs/config, except tooling one-line versions
    if rel in IGNORE:
        return
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeError as exc:
        ERRORS.append(f"{rel}: unsupported source encoding ({exc})")
        return
    if rel == "frontend/package.json":
        d = json.loads(text)
        if not all(
            k in d for k in ("_file_comment", "_file_responsibility", "_functions_to_implement")
        ):
            ERRORS.append(f"{rel}: missing package.json metadata work order")
        return
    header = text[:1400]
    if "책임:" not in header or "구현할 기능:" not in header:
        ERRORS.append(f"{rel}: missing responsibility/functions in header")
    if (
        "완료 기준:" not in header
        and "완료:" not in header
        and rel not in (".gitignore", ".env.example")
    ):
        ERRORS.append(f"{rel}: missing acceptance criterion")


def main() -> int:
    count = 0
    for p in ROOT.rglob("*"):
        if (
            not p.is_file()
            or "__pycache__" in p.parts
            or any(part in GENERATED_DIRS for part in p.relative_to(ROOT).parts)
            or p.suffix == ".pyc"
        ):
            continue
        # Generated binary files and downloaded cache must not be committed
        if p.suffix in (".zip", ".pdf", ".png", ".jpg", ".webp", ".lock", ".tsbuildinfo"):
            continue
        if p.suffix not in TEXT_SUFFIXES and p.name not in TEXT_FILENAMES:
            continue
        count += 1
        check_file(p)
    for err in ERRORS:
        print("FAIL", err)
    print(f"Contract file checks: {count} files; problems={len(ERRORS)}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
