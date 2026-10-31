# 담당: [통합] | 책임: 개인 개발 설정의 안전한 입력·저장·전달.
# 구현: 숨김 입력, 사용자 전용 JSON 저장, 자식 환경 전달.
# 경계: 설정값·개인 경로를 출력하거나 저장소에 기록하지 않는다.
# 완료: POSIX 0600 설정 파일을 만들고 선택한 프로필 설정을 전달한다.
"""개인 개발 설정을 화면에 노출하지 않고 명령에 전달한다."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import secrets
import stat
import sys
import tempfile
import warnings
from pathlib import Path

CONFIG_VERSION = 1
CONFIG_FORMAT = "starter-kit-encrypted-config"
CONFIG_FORMAT_VERSION = 1
CONFIG_KDF = "argon2id"
CONFIG_KDF_MEMORY_KIB = 65536
CONFIG_KDF_ITERATIONS = 3
CONFIG_KDF_LANES = 4
CONFIG_CIPHER = "aes-256-gcm"
CONFIG_AAD = b"starter-kit-config:1"
CONFIG_DIR_NAME = "starter-kit"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b-instruct"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

ENV_KEYS = frozenset(
    {
        "APP_ENV",
        "DATABASE_URL",
        "FRONTEND_ORIGIN",
        "JWT_SIGNING_KEY",
        "CSRF_SECRET",
        "HANDOFF_HASH_KEY",
        "HANDOFF_SERVER_SECRET",
        "RAG_COLLECTION_ID",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "LAW_OC",
        "LLM_PROVIDER",
        "CLASSIFIER_PROVIDER",
        "LLM_AUTO_FALLBACK",
        "LLM_FAILOVER_PROVIDERS",
        "LLM_OLLAMA_BASE_URL",
        "LLM_OLLAMA_MODEL",
        "RAG_DATABASE_URL",
        "RAG_LOCAL_DATABASE_NAME",
        "RAG_TOKENIZER_PATH",
        "RAG_CHUNKING_PROVIDER",
        "RAG_CHUNKING_MODEL",
        "RAG_CHUNKING_OLLAMA_BASE_URL",
        "RAG_CHUNKING_GEMINI_API_KEY",
    }
)
PROFILE_ENV_KEYS = {
    "llm": frozenset(
        {
            "GEMINI_API_KEY",
            "GROQ_API_KEY",
            "LLM_PROVIDER",
            "CLASSIFIER_PROVIDER",
            "LLM_AUTO_FALLBACK",
            "LLM_FAILOVER_PROVIDERS",
            "LLM_OLLAMA_BASE_URL",
            "LLM_OLLAMA_MODEL",
        }
    ),
    "rag": frozenset(
        {
            "RAG_DATABASE_URL",
            "RAG_LOCAL_DATABASE_NAME",
            "RAG_TOKENIZER_PATH",
            "RAG_CHUNKING_PROVIDER",
            "RAG_CHUNKING_MODEL",
            "RAG_CHUNKING_OLLAMA_BASE_URL",
            "RAG_CHUNKING_GEMINI_API_KEY",
        }
    ),
}


class LocalEnvError(Exception):
    """개인 설정을 안전하게 읽거나 쓸 수 없는 경우."""


def config_dir() -> Path:
    return Path.home() / ".config" / CONFIG_DIR_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def _check_owner(path: Path, metadata: os.stat_result) -> None:
    if os.name == "posix" and hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise LocalEnvError("개인 설정 파일의 소유자를 확인할 수 없습니다.")


def _validate_config_data(data: object) -> dict[str, object]:
    if (
        not isinstance(data, dict)
        or data.get("version") != CONFIG_VERSION
        or data.get("profile") not in (None, "inheritance", "llm", "rag")
        or not isinstance(data.get("ollama_extra"), bool)
        or not isinstance(data.get("env"), dict)
        or any(
            key not in ENV_KEYS or not isinstance(value, str) or "\x00" in value
            for key, value in data["env"].items()
        )
    ):
        raise LocalEnvError("개인 설정 파일 형식이 올바르지 않습니다.")
    return data


def _derive_config_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    return Argon2id(
        salt=salt,
        length=32,
        iterations=CONFIG_KDF_ITERATIONS,
        lanes=CONFIG_KDF_LANES,
        memory_cost=CONFIG_KDF_MEMORY_KIB,
    ).derive(passphrase.encode("utf-8"))


def _encrypt_config(data: dict[str, object], passphrase: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    validated = _validate_config_data(data)
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = _derive_config_key(passphrase, salt)
    plaintext = json.dumps(validated, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, CONFIG_AAD)
    envelope = {
        "format": CONFIG_FORMAT,
        "version": CONFIG_FORMAT_VERSION,
        "kdf": {
            "name": CONFIG_KDF,
            "memory_kib": CONFIG_KDF_MEMORY_KIB,
            "iterations": CONFIG_KDF_ITERATIONS,
            "lanes": CONFIG_KDF_LANES,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "cipher": {
            "name": CONFIG_CIPHER,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        },
    }
    return (json.dumps(envelope, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")


def _decrypt_config(payload: bytes, passphrase: str) -> dict[str, object]:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        envelope = json.loads(payload.decode("utf-8"))
        if (
            not isinstance(envelope, dict)
            or envelope.get("format") != CONFIG_FORMAT
            or envelope.get("version") != CONFIG_FORMAT_VERSION
        ):
            raise ValueError
        kdf = envelope["kdf"]
        cipher = envelope["cipher"]
        if (
            not isinstance(kdf, dict)
            or kdf.get("name") != CONFIG_KDF
            or kdf.get("memory_kib") != CONFIG_KDF_MEMORY_KIB
            or kdf.get("iterations") != CONFIG_KDF_ITERATIONS
            or kdf.get("lanes") != CONFIG_KDF_LANES
            or not isinstance(cipher, dict)
            or cipher.get("name") != CONFIG_CIPHER
        ):
            raise ValueError
        salt = base64.b64decode(kdf["salt"], validate=True)
        nonce = base64.b64decode(cipher["nonce"], validate=True)
        ciphertext = base64.b64decode(cipher["ciphertext"], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError
        plaintext = AESGCM(_derive_config_key(passphrase, salt)).decrypt(
            nonce, ciphertext, CONFIG_AAD
        )
        return _validate_config_data(json.loads(plaintext.decode("utf-8")))
    except (InvalidTag, KeyError, TypeError, ValueError, UnicodeError):
        raise LocalEnvError(
            "개인 설정을 열 수 없습니다. 암호 문구를 확인하거나 bootstrap 설정을 다시 실행하세요."
        ) from None


def _read_hidden_passphrase(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(prompt)
    except (EOFError, OSError, getpass.GetPassWarning):
        raise LocalEnvError("암호 문구 입력은 실제 터미널에서만 할 수 있습니다.") from None
    if not value or "\x00" in value:
        raise LocalEnvError("암호 문구가 비어 있거나 형식이 올바르지 않습니다.")
    return value


def _secure_directory() -> Path:
    directory = config_dir()
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise LocalEnvError("개인 설정 디렉터리가 안전한 일반 디렉터리가 아닙니다.")
        _check_owner(directory, metadata)
        if os.name == "posix":
            os.chmod(directory, 0o700)
    except LocalEnvError:
        raise
    except OSError:
        raise LocalEnvError("개인 설정 디렉터리를 안전하게 준비할 수 없습니다.") from None
    return directory


def read_config(passphrase: str | None = None, *, allow_legacy: bool = False) -> dict[str, object]:
    path = config_path()
    if not path.exists() and not path.is_symlink():
        return {"version": CONFIG_VERSION, "profile": None, "ollama_extra": False, "env": {}}
    try:
        _secure_directory()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise LocalEnvError("개인 설정 파일이 안전한 일반 파일이 아닙니다.")
        _check_owner(path, metadata)
        if os.name == "posix" and metadata.st_mode & 0o077:
            os.chmod(path, 0o600)
        payload = path.read_bytes()
        if len(payload) > 1_048_576:
            raise LocalEnvError("개인 설정 파일 크기가 허용 범위를 넘었습니다.")
        envelope = json.loads(payload.decode("utf-8"))
        if isinstance(envelope, dict) and envelope.get("format") == CONFIG_FORMAT:
            passphrase = passphrase or _read_hidden_passphrase("개인 설정 암호 문구: ")
            return _decrypt_config(payload, passphrase)
        if not allow_legacy:
            raise LocalEnvError(
                "암호화되지 않은 개인 설정을 발견했습니다. bash scripts/bootstrap.sh로 다시 설정하세요."
            )
        data = envelope
    except LocalEnvError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise LocalEnvError("개인 설정 파일을 안전하게 읽을 수 없습니다.") from None

    return _validate_config_data(data)


def write_config(data: dict[str, object], passphrase: str) -> None:
    directory = _secure_directory()
    path = directory / "config.json"
    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        if path.is_symlink():
            raise LocalEnvError("개인 설정 파일이 안전한 일반 파일이 아닙니다.")
        descriptor, raw_path = tempfile.mkstemp(prefix=".config-", dir=directory)
        temporary_path = Path(raw_path)
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        encrypted_payload = _encrypt_config(data, passphrase)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encrypted_payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        if os.name == "posix":
            os.chmod(path, 0o600)
    except LocalEnvError:
        raise
    except OSError:
        raise LocalEnvError("개인 설정을 안전하게 저장할 수 없습니다.") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _ask_choice(label: str, choices: tuple[str, ...], default: str) -> str:
    choices_text = "/".join(choices)
    while True:
        answer = input(f"{label} [{choices_text}] (기본값 {default}): ").strip().lower()
        selected = answer or default
        if selected in choices:
            return selected
        print(f"{choices_text} 중 하나를 선택하세요.", file=sys.stderr)


def _ask_text(label: str, default: str) -> str:
    answer = input(f"{label} (기본값 {default}): ").strip()
    return answer or default


def _ask_hidden(env: dict[str, str], key: str, *, label: str | None = None) -> None:
    if env.get(key):
        replace = input(f"{key}가 저장되어 있습니다. 교체할까요? [y/N]: ").strip().lower()
        if replace not in ("y", "yes"):
            return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(f"{label or key} (Enter로 건너뛰기): ")
    except (EOFError, OSError, getpass.GetPassWarning):
        raise LocalEnvError(
            "입력 숨김을 사용할 수 없습니다. 실제 터미널에서 다시 실행하세요."
        ) from None
    if "\x00" in value:
        raise LocalEnvError("입력값 형식이 올바르지 않습니다.")
    if value:
        env[key] = value


def _ensure_tty() -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise LocalEnvError("비밀값 입력은 실제 터미널에서만 할 수 있습니다.")


def _configure_inheritance(env: dict[str, str]) -> None:
    env.setdefault("APP_ENV", "development")
    env.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")
    env.setdefault("LLM_PROVIDER", "gemini")
    env.setdefault("CLASSIFIER_PROVIDER", "gemini")
    env.setdefault("LLM_AUTO_FALLBACK", "false")
    env.setdefault("LLM_FAILOVER_PROVIDERS", "groq")
    env.setdefault("SMTP_PORT", "587")
    for key in (
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "LAW_OC",
        "HANDOFF_SERVER_SECRET",
        "RAG_COLLECTION_ID",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
    ):
        _ask_hidden(env, key)
    for key in ("JWT_SIGNING_KEY", "CSRF_SECRET", "HANDOFF_HASH_KEY"):
        if not env.get(key):
            env[key] = secrets.token_urlsafe(48)


def _configure_llm(env: dict[str, str], ollama_extra: bool) -> None:
    current_provider = env.get("LLM_PROVIDER", "gemini")
    if current_provider not in ("gemini", "groq"):
        current_provider = "gemini"
    provider = _ask_choice("기본 LLM 공급자", ("gemini", "groq"), current_provider)
    env["LLM_PROVIDER"] = provider
    env["CLASSIFIER_PROVIDER"] = provider
    env["LLM_AUTO_FALLBACK"] = "false"
    if provider == "gemini":
        _ask_hidden(env, "GEMINI_API_KEY")
        _ask_hidden(env, "GROQ_API_KEY", label="선택적 Groq 전환 키")
        fallback = "groq"
    else:
        _ask_hidden(env, "GROQ_API_KEY")
        fallback = "none"
    if ollama_extra:
        env.setdefault("LLM_OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
        env.setdefault("LLM_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        fallback = f"{fallback},ollama" if fallback != "none" else "ollama"
    env["LLM_FAILOVER_PROVIDERS"] = fallback


def _configure_rag(env: dict[str, str]) -> None:
    _ask_hidden(env, "RAG_DATABASE_URL", label="로컬 RAG 데이터베이스 URL")
    _ask_hidden(env, "RAG_TOKENIZER_PATH", label="로컬 토크나이저 경로")
    current_provider = env.get("RAG_CHUNKING_PROVIDER", "skip")
    if current_provider not in ("skip", "ollama", "gemini"):
        current_provider = "skip"
    provider = _ask_choice(
        "RAG 청킹 공급자",
        ("skip", "ollama", "gemini"),
        current_provider,
    )
    if provider == "skip":
        for key in (
            "RAG_CHUNKING_PROVIDER",
            "RAG_CHUNKING_MODEL",
            "RAG_CHUNKING_OLLAMA_BASE_URL",
        ):
            env.pop(key, None)
        return
    env["RAG_CHUNKING_PROVIDER"] = provider
    if provider == "ollama":
        env["RAG_CHUNKING_MODEL"] = _ask_text(
            "RAG_CHUNKING_MODEL", env.get("RAG_CHUNKING_MODEL", DEFAULT_OLLAMA_MODEL)
        )
        _ask_hidden(
            env,
            "RAG_CHUNKING_OLLAMA_BASE_URL",
            label="RAG Ollama 서버 URL (비우면 localhost)",
        )
    else:
        env["RAG_CHUNKING_MODEL"] = _ask_text(
            "Gemini 모델 ID", env.get("RAG_CHUNKING_MODEL", DEFAULT_GEMINI_MODEL)
        )
        _ask_hidden(env, "RAG_CHUNKING_GEMINI_API_KEY")


def _new_config_passphrase() -> str:
    passphrase = _read_hidden_passphrase("새 개인 설정 암호 문구: ")
    confirmation = _read_hidden_passphrase("암호 문구를 다시 입력하세요: ")
    if passphrase != confirmation:
        raise LocalEnvError("암호 문구가 일치하지 않습니다. 설정을 저장하지 않았습니다.")
    if len(passphrase) < 12:
        raise LocalEnvError("암호 문구는 12자 이상이어야 합니다. 설정을 저장하지 않았습니다.")
    return passphrase


def configure(profile: str, ollama_extra: bool, *, doctor_check: bool = False) -> int:
    _ensure_tty()
    data = read_config(allow_legacy=True)
    env = dict(data["env"])
    if profile == "inheritance":
        _configure_inheritance(env)
    elif profile == "llm":
        _configure_llm(env, ollama_extra)
    else:
        _configure_rag(env)
    data["profile"] = profile
    data["ollama_extra"] = ollama_extra
    data["env"] = env
    passphrase = _new_config_passphrase()
    write_config(data, passphrase)
    print("개인 설정을 저장했습니다. 비밀값은 화면에 출력하지 않았습니다.")
    if doctor_check:
        import doctor

        return doctor.run(profile, check_installed=True, config=data)
    return 0


def runtime_env(data: dict[str, object]) -> dict[str, str]:
    """실행 프로필과 선택 공급자가 사용하는 설정만 반환한다."""
    profile = data["profile"]
    env = data["env"]
    if profile == "inheritance":
        return dict(env)
    if profile not in PROFILE_ENV_KEYS:
        return {}
    selected = {key: value for key, value in env.items() if key in PROFILE_ENV_KEYS[profile]}
    if profile == "llm" and "ollama" not in env.get("LLM_FAILOVER_PROVIDERS", ""):
        selected.pop("LLM_OLLAMA_BASE_URL", None)
        selected.pop("LLM_OLLAMA_MODEL", None)
    if profile == "rag":
        provider = env.get("RAG_CHUNKING_PROVIDER")
        if provider != "gemini":
            selected.pop("RAG_CHUNKING_GEMINI_API_KEY", None)
        if provider != "ollama":
            selected.pop("RAG_CHUNKING_OLLAMA_BASE_URL", None)
        if provider not in ("gemini", "ollama"):
            for key in ("RAG_CHUNKING_PROVIDER", "RAG_CHUNKING_MODEL"):
                selected.pop(key, None)
    return selected


def run_command(command: list[str]) -> int:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("실행할 명령을 지정하세요.", file=sys.stderr)
        return 2
    try:
        data = read_config()
    except LocalEnvError as error:
        print(str(error), file=sys.stderr)
        return 2
    child_env = os.environ.copy()
    for key, value in runtime_env(data).items():
        child_env.setdefault(key, value)
    try:
        os.execvpe(command[0], command, child_env)
    except OSError:
        print(
            "명령을 시작할 수 없습니다. 명령 이름과 설치 상태를 확인하세요.",
            file=sys.stderr,
        )
        return 127
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="local_env.py")
    subparsers = parser.add_subparsers(dest="action", required=True)
    configure_parser = subparsers.add_parser("configure", help="선택 프로필의 개인 설정 입력")
    configure_parser.add_argument("--profile", choices=("inheritance", "llm", "rag"), required=True)
    configure_parser.add_argument(
        "--ollama-failover", action=argparse.BooleanOptionalAction, default=False
    )
    configure_parser.add_argument(
        "--doctor-check", action="store_true", help="설정 후 해독된 설정으로 doctor를 실행"
    )
    run_parser = subparsers.add_parser("run", help="개인 설정을 적용해 명령 실행")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == "configure":
            return configure(args.profile, args.ollama_failover, doctor_check=args.doctor_check)
        return run_command(args.command)
    except LocalEnvError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("설정 작업을 중단했습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
