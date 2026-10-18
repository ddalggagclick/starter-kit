# 책임: [C] LLM 패키지의 독립 CLI 진입점.
# 구현할 기능: 설정 확인 및 GenerationRequest DTO 검증 명령 제공.
# 코드 경계: 실제 Gemini/Ollama 호출 및 자동 fallback을 구현하거나 흉내 내지 않는다.
# 완료 기준: starter-llm --help / status / validate 명령이 오프라인에서 동작한다.
from __future__ import annotations

import argparse
import json
import os

from starter_llm.contracts.models import GenerationRequest, ModelMessage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-llm", description="LLM 계약 확인용 CLI (실제 모델 호출 미구현)"
    )
    cmd = parser.add_subparsers(dest="command", required=True)
    cmd.add_parser("status", help="모델 설정/구현 상태 확인 (외부 호출 없음)")
    validate = cmd.add_parser("validate", help="생성 요청 DTO 검증 (외부 호출 없음)")
    validate.add_argument("--prompt", required=True)
    validate.add_argument("--profile", default="default")
    validate.add_argument("--request-id", default="cli-check")
    validate.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(
            json.dumps(
                {
                    "package": "starter-llm",
                    "status": "contract-only",
                    "provider": os.getenv("LLM_PROVIDER", "gemini"),
                    "generationImplemented": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    try:
        req = GenerationRequest(
            messages=(ModelMessage(role="user", content=args.prompt),),
            model_profile=args.profile,
            request_id=args.request_id,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        parser.exit(2, f"잘못된 LLM 요청: {exc}\n")
    print(
        json.dumps(
            {
                "valid": True,
                "profile": req.model_profile,
                "timeoutSeconds": req.timeout_seconds,
                "messageCount": len(req.messages),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
