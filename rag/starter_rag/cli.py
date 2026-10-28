# 책임: [D] RAG 패키지의 독립 CLI 진입점.
# 구현할 기능: 공개 검색 요청 검증 및 RAG 구성 확인.
# 코드 경계: Docling 적재/pgvector 검색/DB 변경은 구현하지 않는다.
# 완료 기준: starter-rag --help / status / validate-search 명령이 오프라인에서 동작한다.
from __future__ import annotations

import argparse
import json

from starter_rag.contracts.models import SearchRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-rag", description="RAG 계약 확인용 CLI (실제 검색/적재 미구현)"
    )
    cmd = parser.add_subparsers(dest="command", required=True)
    cmd.add_parser("status", help="검색/적재 구현 상태 확인 (DB 연결 없음)")
    validate = cmd.add_parser("validate-search", help="검색 요청 DTO 검증 (DB 연결 없음)")
    validate.add_argument("--query", required=True)
    validate.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(
            json.dumps(
                {
                    "package": "starter-rag",
                    "status": "contract-only",
                    "searchImplemented": False,
                    "ingestionImplemented": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    try:
        req = SearchRequest(query=args.query, top_k=args.top_k)
    except ValueError as exc:
        parser.exit(2, f"잘못된 RAG 검색 요청: {exc}\n")
    print(json.dumps({"valid": True, "query": req.query, "topK": req.top_k}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
