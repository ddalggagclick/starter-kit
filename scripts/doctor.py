# 담당: [통합] | 책임: 선택한 개발 프로필의 도구·설치·설정 상태 점검.
# 구현: Python/uv와 프로필별 도구·lockfile·설정 여부 점검.
# 경계: DB/API에 연결하지 않고 비밀값·개인 경로를 출력하지 않는다.
# 완료: 도구/설치 실패는 종료 코드 1, 선택 설정 누락은 상태만 표시한다.
"""선택 프로필의 로컬 준비 상태를 값 노출 없이 확인한다."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from local_env import LocalEnvError, read_config

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""
    guide: str = ""


INSTALL_GUIDES = {
    "Python 3.13": "https://www.python.org/downloads/",
    "uv": "https://docs.astral.sh/uv/getting-started/installation/",
    "Node.js 24.22.1+": "https://nodejs.org/en/download/",
    "npm": "https://docs.npmjs.com/downloading-and-installing-node-js-and-npm/",
    "PostgreSQL": "https://www.postgresql.org/download/",
    "pgvector": "https://github.com/pgvector/pgvector#installation",
    "Ollama": "https://ollama.com/download",
}


def _version_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip()


def _node_version() -> tuple[bool, str]:
    version = _version_output(["node", "--version"])
    if version is None:
        return False, "not found"
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if match is None:
        return False, "version unreadable"
    numeric = tuple(int(part) for part in match.groups())
    return numeric >= (24, 22, 1), ".".join(str(part) for part in numeric)


def prerequisites(profile: str) -> list[Check]:
    checks = [
        Check("POSIX file permissions", os.name == "posix"),
        Check(
            "Python 3.13",
            sys.version_info.major == 3 and sys.version_info.minor == 13,
            f"{sys.version_info.major}.{sys.version_info.minor}",
            INSTALL_GUIDES["Python 3.13"],
        ),
        Check("uv", shutil.which("uv") is not None, guide=INSTALL_GUIDES["uv"]),
        Check("uv.lock", (ROOT / "uv.lock").is_file()),
    ]
    if profile == "inheritance":
        node_ok, node_detail = _node_version()
        checks.extend(
            [
                Check(
                    "Node.js 24.22.1+",
                    node_ok,
                    node_detail,
                    INSTALL_GUIDES["Node.js 24.22.1+"],
                ),
                Check(
                    "npm",
                    shutil.which("npm") is not None,
                    guide=INSTALL_GUIDES["npm"],
                ),
                Check(
                    "frontend/package-lock.json",
                    (ROOT / "frontend/package-lock.json").is_file(),
                ),
            ]
        )
    return checks


def _print_checks(checks: list[Check]) -> bool:
    all_ok = True
    for check in checks:
        status = "OK" if check.ok else "MISSING"
        detail = f" ({check.detail})" if check.detail else ""
        print(f"{check.name}: {status}{detail}")
        if not check.ok and check.guide:
            print(f"  공식 설치 안내: {check.guide}")
        all_ok = all_ok and check.ok
    return all_ok


def _postgres_install_checks() -> list[Check]:
    pg_config = shutil.which("pg_config")
    if pg_config is None:
        return [
            Check(
                "PostgreSQL client tools (pg_config)",
                False,
                guide=INSTALL_GUIDES["PostgreSQL"],
            ),
            Check(
                "PostgreSQL server (postgres)",
                shutil.which("postgres") is not None,
                guide=INSTALL_GUIDES["PostgreSQL"],
            ),
            Check("pgvector extension files", False, guide=INSTALL_GUIDES["pgvector"]),
        ]

    bindir = _version_output([pg_config, "--bindir"])
    sharedir = _version_output([pg_config, "--sharedir"])
    server_exists = bool(
        bindir
        and (Path(bindir) / "postgres").is_file()
        and os.access(Path(bindir) / "postgres", os.X_OK)
    )
    if not server_exists:
        server_exists = shutil.which("postgres") is not None
    vector_exists = bool(sharedir and (Path(sharedir) / "extension" / "vector.control").is_file())
    return [
        Check("PostgreSQL client tools (pg_config)", True),
        Check(
            "PostgreSQL server (postgres)",
            server_exists,
            guide="" if server_exists else INSTALL_GUIDES["PostgreSQL"],
        ),
        Check(
            "pgvector extension files",
            vector_exists,
            guide="" if vector_exists else INSTALL_GUIDES["pgvector"],
        ),
    ]


def runtime_prerequisites(profile: str, config: dict[str, object]) -> list[Check]:
    """선택 프로필의 실행 전제만 검사하며 외부 서비스에는 연결하지 않는다."""
    raw_env = config.get("env", {})
    env = raw_env if isinstance(raw_env, dict) else {}
    checks: list[Check] = []

    if profile == "inheritance":
        checks.extend(
            [
                Check("DATABASE_URL", bool(env.get("DATABASE_URL"))),
                Check("RAG_COLLECTION_ID", bool(env.get("RAG_COLLECTION_ID"))),
                Check("LLM provider keys", _has_primary_model_key(env)),
                Check("LAW_OC", bool(env.get("LAW_OC"))),
            ]
        )
    elif profile == "llm":
        provider = env.get("LLM_PROVIDER", "gemini")
        key_name = "GEMINI_API_KEY" if provider == "gemini" else "GROQ_API_KEY"
        checks.append(Check(f"{provider} provider key", bool(env.get(key_name))))
    elif profile == "rag":
        checks.extend(
            [
                Check("RAG_DATABASE_URL", bool(env.get("RAG_DATABASE_URL"))),
                Check("RAG_TOKENIZER_PATH", bool(env.get("RAG_TOKENIZER_PATH"))),
                *_postgres_install_checks(),
            ]
        )
        chunking_provider = env.get("RAG_CHUNKING_PROVIDER")
        if chunking_provider == "gemini":
            checks.append(
                Check("RAG chunking provider key", bool(env.get("RAG_CHUNKING_GEMINI_API_KEY")))
            )

    failovers = str(env.get("LLM_FAILOVER_PROVIDERS", "")).split(",")
    selected_ollama = profile == "llm" and "ollama" in {name.strip() for name in failovers}
    selected_ollama = selected_ollama or (
        profile == "rag" and env.get("RAG_CHUNKING_PROVIDER") == "ollama"
    )
    if selected_ollama:
        ollama_found = shutil.which("ollama") is not None
        checks.append(
            Check(
                "Ollama executable",
                ollama_found,
                guide="" if ollama_found else INSTALL_GUIDES["Ollama"],
            )
        )
    if profile == "inheritance":
        checks.append(
            Check("Frontend API mode (VITE_USE_MOCK_API=false)", _frontend_api_configured())
        )
    return checks


def show_runtime_prerequisites(
    profile: str, config: dict[str, object], checks: list[Check]
) -> None:
    setting_names = {
        "DATABASE_URL",
        "RAG_COLLECTION_ID",
        "LLM provider keys",
        "LAW_OC",
        "RAG_DATABASE_URL",
        "RAG_TOKENIZER_PATH",
        "RAG chunking provider key",
    }
    runtime_ok = True
    for check in checks:
        is_setting = (
            check.name in setting_names
            or check.name.endswith(" provider key")
            or check.name.startswith("Frontend API mode")
        )
        if is_setting:
            print(f"{check.name}: {'configured' if check.ok else 'missing'}")
        elif check.ok:
            print(f"RUNTIME PREREQUISITE: READY — {check.name}")
        else:
            runtime_ok = False
            print(f"RUNTIME PREREQUISITE: MISSING — {check.name}")
            if check.guide:
                print(f"  공식 설치 안내: {check.guide}")
        if not check.ok:
            runtime_ok = False
            if is_setting:
                print(f"RUNTIME PREREQUISITE: MISSING — {check.name}")
                if check.guide:
                    print(f"  공식 설치 안내: {check.guide}")
    if profile == "rag":
        print("PostgreSQL service status: NOT CHECKED")
    env = config.get("env", {})
    if isinstance(env, dict):
        failovers = {name.strip() for name in str(env.get("LLM_FAILOVER_PROVIDERS", "")).split(",")}
        if (profile == "llm" and "ollama" in failovers) or (
            profile == "rag" and env.get("RAG_CHUNKING_PROVIDER") == "ollama"
        ):
            print("Ollama service and selected model status: NOT CHECKED")
    print(f"Local program/config prerequisites: {'READY' if runtime_ok else 'INCOMPLETE'}")


def _profile_sync_command(
    profile: str, config: dict[str, object], *, check: bool = True
) -> list[str]:
    command = ["uv", "sync"]
    if check:
        command.append("--check")
    command.extend(["--locked", "--group", "bootstrap"])
    if profile == "llm":
        command.extend(["--package", "starter-llm"])
        env = config.get("env", {})
        ollama_enabled = bool(config.get("ollama_extra"))
        if isinstance(env, dict) and "ollama" in env.get("LLM_FAILOVER_PROVIDERS", ""):
            ollama_enabled = True
        if ollama_enabled:
            command.extend(["--extra", "ollama"])
    elif profile == "rag":
        command.extend(["--package", "starter-rag", "--extra", "ingestion"])
    return command


def _dependencies_match(profile: str, config: dict[str, object]) -> bool:
    command = _profile_sync_command(profile, config)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _npm_dependencies_match() -> bool:
    try:
        result = subprocess.run(
            ["npm", "ls", "--depth=0", "--prefix", "frontend"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _has_primary_model_key(env: dict[str, str]) -> bool:
    providers = {env.get("LLM_PROVIDER", "gemini"), env.get("CLASSIFIER_PROVIDER", "gemini")}
    return all(
        (provider == "gemini" and bool(env.get("GEMINI_API_KEY")))
        or (provider == "groq" and bool(env.get("GROQ_API_KEY")))
        for provider in providers
    )


def _frontend_api_configured() -> bool:
    frontend_env = ROOT / "frontend" / ".env.development"
    try:
        frontend_values = {}
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                frontend_values[key.strip()] = value.strip()
    except (OSError, UnicodeError):
        return False
    return (
        frontend_values.get("VITE_API_BASE_URL") == "http://localhost:8000"
        and frontend_values.get("VITE_USE_MOCK_API") == "false"
    )


def run(
    profile: str,
    *,
    check_installed: bool,
    config: dict[str, object] | None = None,
) -> int:
    checks = prerequisites(profile)
    if not _print_checks(checks):
        return 1
    if not check_installed:
        return 0

    if config is None:
        try:
            config = read_config()
        except LocalEnvError:
            print("Private settings: unavailable")
            print("설정을 읽을 수 없습니다. bash scripts/bootstrap.sh를 실행해 다시 설정하세요.")
            return 1
    env = config["env"]
    if not isinstance(env, dict):
        print("Private settings: unavailable")
        return 1

    python_ok = _dependencies_match(profile, config)
    print(f"Python dependencies: {'OK' if python_ok else 'MISSING'}")
    all_ok = python_ok
    if not python_ok:
        command = _profile_sync_command(profile, config, check=False)
        print(f"재설치 명령: {' '.join(command)}")
    if profile == "inheritance":
        npm_ok = _npm_dependencies_match()
        print(f"Frontend dependencies: {'OK' if npm_ok else 'MISSING'}")
        if not npm_ok:
            print("재설치 명령: npm ci --prefix frontend")
        all_ok = all_ok and npm_ok

    print(f"Python/npm dependency installation: {'COMPLETE' if all_ok else 'INCOMPLETE'}")
    runtime_checks = runtime_prerequisites(profile, config)
    show_runtime_prerequisites(profile, config, runtime_checks)
    print("Live DB/API/model connectivity: not checked")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doctor.py")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "check"):
        command_parser = commands.add_parser(action)
        command_parser.add_argument(
            "--profile", choices=("inheritance", "llm", "rag"), required=True
        )
    args = parser.parse_args(argv)
    return run(args.profile, check_installed=args.action == "check")


if __name__ == "__main__":
    sys.exit(main())
