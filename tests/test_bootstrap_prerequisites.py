from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import doctor


def _check_names(checks: list[doctor.Check]) -> set[str]:
    return {check.name for check in checks}


def test_llm_profile_does_not_require_postgresql() -> None:
    checks = doctor.runtime_prerequisites("llm", {"env": {}})

    assert not any("PostgreSQL" in name or "pgvector" in name for name in _check_names(checks))


def test_full_profile_requires_node_and_npm(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_node_version", lambda: (False, "not found"))
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)

    checks = doctor.prerequisites("inheritance")

    assert {"Node.js 24.22.1+", "npm"} <= _check_names(checks)
    assert not next(check for check in checks if check.name == "Node.js 24.22.1+").ok
    assert not next(check for check in checks if check.name == "npm").ok
    assert doctor.run("inheritance", check_installed=False) == 1


def test_missing_python_or_uv_blocks_preflight(monkeypatch) -> None:
    monkeypatch.setattr(doctor.sys, "version_info", SimpleNamespace(major=3, minor=12))
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)
    checks = doctor.prerequisites("llm")
    names = {check.name: check.ok for check in checks}

    assert names["Python 3.13"] is False
    assert names["uv"] is False
    monkeypatch.setattr(doctor, "prerequisites", lambda _profile: checks)

    def forbidden_read_config() -> dict[str, object]:
        raise AssertionError("설정 파일은 preflight에서 읽으면 안 됩니다.")

    monkeypatch.setattr(doctor, "read_config", forbidden_read_config)

    assert doctor.run("llm", check_installed=False) == 1


def test_bootstrap_menu_uses_bash_3_2_compatible_case_syntax() -> None:
    script = (doctor.ROOT / "scripts" / "bootstrap.sh").read_text(encoding="utf-8")

    assert "${ollama_answer,,}" not in script
    assert 'case "$ollama_answer" in' in script


def test_rag_profile_reports_postgresql_and_pgvector(monkeypatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)

    checks = doctor.runtime_prerequisites("rag", {"env": {}})

    names = _check_names(checks)
    assert "PostgreSQL client tools (pg_config)" in names
    assert "PostgreSQL server (postgres)" in names
    assert "pgvector extension files" in names


def test_full_profile_reports_remote_settings_presence_only(capsys) -> None:
    config = {
        "env": {
            "DATABASE_URL": "postgresql://synthetic-user:synthetic-password@db.invalid/app",
            "RAG_COLLECTION_ID": "synthetic-collection-secret",
            "GEMINI_API_KEY": "synthetic-provider-key",
            "LAW_OC": "synthetic-law-key",
            "LLM_PROVIDER": "gemini",
            "CLASSIFIER_PROVIDER": "gemini",
        }
    }

    checks = doctor.runtime_prerequisites("inheritance", config)
    doctor.show_runtime_prerequisites("inheritance", config, checks)
    output = capsys.readouterr().out

    assert all(check.ok for check in checks)
    assert "DATABASE_URL: configured" in output
    assert "RAG_COLLECTION_ID: configured" in output
    assert "synthetic-" not in output


def test_selected_ollama_reports_missing_executable(monkeypatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)
    config = {"env": {"LLM_FAILOVER_PROVIDERS": "groq,ollama"}}

    checks = doctor.runtime_prerequisites("llm", config)

    ollama = next(check for check in checks if check.name == "Ollama executable")
    assert not ollama.ok


def test_missing_runtime_program_prints_install_guide_without_secret_values(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)
    config = {"env": {"RAG_DATABASE_URL": "postgresql://synthetic:secret@db.invalid/rag"}}

    checks = doctor.runtime_prerequisites("rag", config)
    doctor.show_runtime_prerequisites("rag", config, checks)
    output = capsys.readouterr().out

    assert "RUNTIME PREREQUISITE: MISSING" in output
    assert "https://www.postgresql.org/download/" in output
    assert "https://github.com/pgvector/pgvector" in output
    assert "synthetic" not in output
    assert "db.invalid" not in output


def test_missing_rag_runtime_keeps_successful_package_install_non_blocking(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(doctor, "prerequisites", lambda _profile: [doctor.Check("preflight", True)])
    monkeypatch.setattr(doctor, "_dependencies_match", lambda _profile, _config: True)
    monkeypatch.setattr(doctor, "read_config", lambda: {"env": {}})
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: None)

    result = doctor.run("rag", check_installed=True)
    output = capsys.readouterr().out

    assert result == 0
    assert "Python/npm dependency installation: COMPLETE" in output
    assert "Local program/config prerequisites: INCOMPLETE" in output
