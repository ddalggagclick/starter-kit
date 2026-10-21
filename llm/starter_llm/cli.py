# 책임: [C] LLM 패키지의 독립 CLI 진입점.
# 구현할 기능: 설정 확인, DTO 검증, 실제 생성(generate) 명령 제공.
# 코드 경계: 같은 공급자 재시도 없음, 전환은 설정한 순서(gemini -> groq -> 선택 ollama)만. 비밀값·프롬프트를 출력하지 않는다.
# 완료 기준: status / validate는 오프라인에서 동작하고, generate는 기본 공급자 1회 후 필요 시 다음 공급자를 1회씩만 호출한다.
# 종료 코드: 0 성공, 2 입력·설정 오류, 3 키 없음, 4 사용량 제한(429), 5 시간 초과, 6 공급자 불가, 7 출력 오류
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, ModelMessage
from starter_llm.runtime.settings import LLMSettings, SettingsError

EXIT_CODES = {
    ModelErrorCode.RATE_LIMIT: 4,
    ModelErrorCode.TIMEOUT: 5,
    ModelErrorCode.UNAVAILABLE: 6,
    ModelErrorCode.INVALID_OUTPUT: 7,
    ModelErrorCode.UNSUPPORTED_CAPABILITY: 6,
    ModelErrorCode.CANCELLED: 6,
}


def _print(obj: dict, stream=None) -> None:
    print(json.dumps(obj, ensure_ascii=False), file=stream or sys.stdout)


def _target_json(target) -> dict:
    return {"provider": target.provider, "model": target.model}


def _usable(settings: LLMSettings, purpose: str) -> bool:
    """기본 공급자 또는 전환 대상 중 키가 있는 곳이 하나라도 있어야 호출할 수 있다."""
    return any(settings.api_key_configured(t.provider) for t in settings.chain_for(purpose))


def _settings(parser: argparse.ArgumentParser) -> LLMSettings:
    try:
        return LLMSettings.from_env()
    except SettingsError as exc:
        parser.exit(2, f"잘못된 LLM 설정: {exc}\n")


def _build_request(parser, args, purpose_profile: str) -> GenerationRequest:
    messages = []
    if getattr(args, "system", None):
        messages.append(ModelMessage(role="system", content=args.system))
    messages.append(ModelMessage(role="user", content=args.prompt))
    try:
        return GenerationRequest(
            messages=tuple(messages),
            model_profile=purpose_profile,
            request_id=args.request_id,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        parser.exit(2, f"잘못된 LLM 요청: {exc}\n")


async def _generate(settings: LLMSettings, request: GenerationRequest, purpose: str, stream: bool):
    from starter_llm.runtime.client import ManagedModelResources

    manager = ManagedModelResources(settings)
    port = await manager.acquire(purpose)
    try:
        if stream:
            text = []
            async for chunk in port.stream(request):
                if chunk.text_delta:
                    text.append(chunk.text_delta)
                    print(chunk.text_delta, end="", flush=True)
            print()
            return "".join(text), None
        result = await port.generate(request)
        return result.text, result
    finally:
        await manager.release(purpose)
        await manager.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-llm",
        description="LLM 확인용 CLI (generate: Gemini 1회, 제한·장애 시 Groq(선택 Ollama) 순서로 1회씩. 반복 재시도 없음)",
    )
    cmd = parser.add_subparsers(dest="command", required=True)
    cmd.add_parser("status", help="모델 설정 상태 확인 (외부 호출 없음, 키 값은 출력하지 않음)")

    def add_request_args(p):
        p.add_argument("--prompt", required=True)
        p.add_argument("--request-id", default="cli-check")
        p.add_argument("--timeout", type=float, default=30.0)

    validate = cmd.add_parser("validate", help="생성 요청 DTO 검증 (외부 호출 없음)")
    add_request_args(validate)
    validate.add_argument("--profile", default="default")

    gen = cmd.add_parser("generate", help="실제 생성 1회 (LLM_PROVIDER 설정의 공급자 호출)")
    add_request_args(gen)
    gen.add_argument("--system", default=None, help="시스템 메시지(선택)")
    gen.add_argument("--purpose", choices=("answer", "classifier"), default="answer")
    gen.add_argument("--stream", action="store_true", help="청크 단위로 출력")
    args = parser.parse_args(argv)

    if args.command == "status":
        settings = _settings(parser)
        _print(
            {
                "package": "starter-llm",
                "status": "implemented",
                "generationImplemented": True,
                "answer": {"provider": settings.answer.provider, "model": settings.answer.model},
                "classifier": {
                    "provider": settings.classifier.provider,
                    "model": settings.classifier.model,
                },
                "failover": {
                    "answer": [_target_json(t) for t in settings.failover_for("answer")],
                    "classifier": [_target_json(t) for t in settings.failover_for("classifier")],
                    "cooldownSeconds": settings.failover_policy.cooldown_seconds,
                },
                "geminiApiKeyConfigured": settings.api_key_configured("gemini"),
                "groqApiKeyConfigured": settings.api_key_configured("groq"),
            }
        )
        return 0

    if args.command == "validate":
        req = _build_request(parser, args, args.profile)
        _print(
            {
                "valid": True,
                "profile": req.model_profile,
                "timeoutSeconds": req.timeout_seconds,
                "messageCount": len(req.messages),
            }
        )
        return 0

    # generate
    settings = _settings(parser)
    if not _usable(settings, args.purpose):
        _print({"ok": False, "error": "API_KEY_MISSING"}, sys.stderr)  # 키 이름·값은 출력하지 않음
        return 3
    req = _build_request(parser, args, args.purpose)
    try:
        text, result = asyncio.run(_generate(settings, req, args.purpose, args.stream))
    except ModelError as exc:
        _print({"ok": False, "error": exc.code.value, "retryable": exc.retryable}, sys.stderr)
        return EXIT_CODES.get(exc.code, 6)
    info = {"ok": True, "chars": len(text)}
    if result is not None:
        info.update(
            provider=result.provider,  # 실제로 응답한 공급자(전환됐다면 groq)
            model=result.model,
            finishReason=result.finish_reason,
            inputTokens=result.input_tokens,
            outputTokens=result.output_tokens,
        )
        print(text)
    _print(info, sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
