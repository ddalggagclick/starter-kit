from __future__ import annotations

import base64
import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import doctor
import local_env

PASSPHRASE = "synthetic-local-config-passphrase-2026"
API_KEY = "synthetic-api-key-only-for-tests"
DATABASE_URL = (
    "postgresql+asyncpg://synthetic-user:synthetic-db-password@127.0.0.1/starter_rag_integration"
)


def _settings() -> dict[str, object]:
    return {
        "version": 1,
        "profile": "rag",
        "ollama_extra": False,
        "env": {
            "GEMINI_API_KEY": API_KEY,
            "RAG_DATABASE_URL": DATABASE_URL,
        },
    }


def test_encrypted_config_round_trips_with_correct_passphrase() -> None:
    settings = _settings()

    encrypted = local_env._encrypt_config(settings, PASSPHRASE)
    decrypted = local_env._decrypt_config(encrypted, PASSPHRASE)

    assert decrypted == settings


def test_encrypted_config_file_does_not_contain_saved_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = _settings()

    local_env.write_config(settings, PASSPHRASE)
    saved_file = local_env.config_path().read_bytes()

    assert API_KEY.encode() not in saved_file
    assert DATABASE_URL.encode() not in saved_file
    assert local_env.read_config(PASSPHRASE) == settings


def test_configure_persists_encrypted_settings_without_printing_credentials(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(local_env, "_ensure_tty", lambda: None)
    monkeypatch.setattr(local_env.getpass, "getpass", lambda _prompt: PASSPHRASE)

    def configure_llm(env: dict[str, str], _ollama_extra: bool) -> None:
        env["GEMINI_API_KEY"] = API_KEY

    monkeypatch.setattr(local_env, "_configure_llm", configure_llm)

    assert local_env.configure("llm", False) == 0

    output = capsys.readouterr().out
    saved_file = local_env.config_path().read_bytes()
    assert API_KEY not in output
    assert DATABASE_URL not in output
    assert API_KEY.encode() not in saved_file
    assert local_env.read_config(PASSPHRASE)["env"]["GEMINI_API_KEY"] == API_KEY


def test_wrong_passphrase_and_tampered_ciphertext_are_rejected_without_secret_output(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    encrypted = local_env._encrypt_config(_settings(), PASSPHRASE)

    for payload, passphrase in (
        (encrypted, "incorrect test passphrase"),
        (_tamper_ciphertext(encrypted), PASSPHRASE),
    ):
        try:
            local_env._decrypt_config(payload, passphrase)
        except local_env.LocalEnvError as error:
            message = str(error)
        else:
            raise AssertionError("오암호나 변조된 설정을 복호화했습니다.")
        assert API_KEY not in message
        assert DATABASE_URL not in message
        assert str(tmp_path) not in message


def test_encrypted_config_uses_private_directory_and_file_modes(tmp_path, monkeypatch) -> None:
    if os.name != "posix":
        return
    monkeypatch.setenv("HOME", str(tmp_path))

    local_env.write_config(_settings(), PASSPHRASE)

    assert stat.S_IMODE(local_env.config_dir().stat().st_mode) == 0o700
    assert stat.S_IMODE(local_env.config_path().stat().st_mode) == 0o600


def test_configure_prompts_twice_and_migrates_legacy_plaintext(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(local_env, "_ensure_tty", lambda: None)
    local_env.config_path().parent.mkdir(parents=True)
    local_env.config_path().write_text(json.dumps(_settings()), encoding="utf-8")
    passphrase_prompt = Mock(return_value=PASSPHRASE)
    monkeypatch.setattr(local_env.getpass, "getpass", passphrase_prompt)
    monkeypatch.setattr(local_env, "_configure_llm", lambda _env, _ollama: None)

    assert local_env.configure("llm", False) == 0

    assert passphrase_prompt.call_count == 2
    saved_file = local_env.config_path().read_bytes()
    assert API_KEY.encode() not in saved_file
    assert local_env.read_config(PASSPHRASE)["profile"] == "llm"


def test_configure_does_not_save_when_passphrase_confirmation_mismatches(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(local_env, "_ensure_tty", lambda: None)
    monkeypatch.setattr(local_env, "_configure_llm", lambda _env, _ollama: None)
    monkeypatch.setattr(
        local_env.getpass,
        "getpass",
        Mock(side_effect=(PASSPHRASE, "a different synthetic passphrase")),
    )

    try:
        local_env.configure("llm", False)
    except local_env.LocalEnvError as error:
        assert "일치하지 않습니다" in str(error)
    else:
        raise AssertionError("서로 다른 암호 문구를 저장했습니다.")

    assert not local_env.config_path().exists()


def test_run_rejects_legacy_plaintext_until_bootstrap_migrates_it(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    local_env.config_path().parent.mkdir(parents=True)
    local_env.config_path().write_text(json.dumps(_settings()), encoding="utf-8")
    exec_command = Mock()
    monkeypatch.setattr(local_env.os, "execvpe", exec_command)

    assert local_env.run_command(["synthetic-command"]) == 2

    assert not exec_command.called
    output = capsys.readouterr().err
    assert "bash scripts/bootstrap.sh" in output
    assert API_KEY not in output
    assert DATABASE_URL not in output


def test_configure_doctor_check_reuses_decrypted_config_without_extra_prompt(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(local_env, "_ensure_tty", lambda: None)
    monkeypatch.setattr(
        local_env, "_configure_llm", lambda env, _ollama: env.update({"GEMINI_API_KEY": API_KEY})
    )
    passphrase_prompt = Mock(return_value=PASSPHRASE)
    monkeypatch.setattr(local_env.getpass, "getpass", passphrase_prompt)
    doctor_run = Mock(return_value=0)
    monkeypatch.setattr(doctor, "run", doctor_run)

    assert local_env.configure("llm", False, doctor_check=True) == 0

    assert passphrase_prompt.call_count == 2
    assert doctor_run.call_args.kwargs["config"]["env"]["GEMINI_API_KEY"] == API_KEY


def _tamper_ciphertext(payload: bytes) -> bytes:
    envelope = json.loads(payload)
    ciphertext = bytearray(base64.b64decode(envelope["cipher"]["ciphertext"]))
    ciphertext[-1] ^= 1
    envelope["cipher"]["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
    return json.dumps(envelope).encode("utf-8")
