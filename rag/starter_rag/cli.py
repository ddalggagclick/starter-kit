# 책임: [D] RAG 패키지의 독립 CLI 진입점.
# 구현할 기능: 공개 검색 요청 검증 및 RAG 구성 확인.
# 코드 경계: Docling 적재/pgvector 검색/DB 변경은 구현하지 않는다.
# 완료 기준: starter-rag --help / status / validate-search 명령이 오프라인에서 동작한다.
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from starter_rag.contracts.models import SearchRequest
from starter_rag.ingestion.parser import (
    DocumentReadError,
    UnsupportedDocumentFormatError,
    extract_document_structure,
    parse_document,
)


def _file_argument(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("파일 경로가 비어 있습니다")
    return value


def _parse_file(path: str) -> int:
    source = Path(path)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            document = parse_document(source)
            structure = extract_document_structure(document, source)
        payload = {
            "input_file": path,
            "success": True,
            "source_format": structure.source_format,
            "element_count": len(structure.elements),
            "elements": [asdict(element) for element in structure.elements],
            "unverified_items": [
                asdict(item) for item in structure.unverified_items
            ],
        }
        output = json.dumps(payload, ensure_ascii=False)
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"문서 파싱에 실패했습니다: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-rag", description="RAG 계약 확인용 CLI (실제 검색/적재 미구현)"
    )
    parser.add_argument("--file", type=_file_argument, metavar="PATH")
    cmd = parser.add_subparsers(dest="command", required=False)
    cmd.add_parser("status", help="검색/적재 구현 상태 확인 (DB 연결 없음)")
    validate = cmd.add_parser("validate-search", help="검색 요청 DTO 검증 (DB 연결 없음)")
    validate.add_argument("--query", required=True)
    validate.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    if args.file is not None and args.command is not None:
        parser.error("--file과 기존 서브커맨드는 함께 사용할 수 없습니다")
    if args.file is not None:
        return _parse_file(args.file)
    if args.command is None:
        parser.error("서브커맨드 또는 --file을 지정해야 합니다")

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
