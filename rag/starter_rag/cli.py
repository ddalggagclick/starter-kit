# 책임: [D] RAG 패키지의 독립 CLI 진입점.
# 구현할 기능: 공개 검색 요청 검증, 파일 파싱, 명시적 청크 생성 확인.
# 코드 경계: 적재/pgvector 검색/DB 변경은 구현하지 않는다.
# 완료 기준: 상태·검색 검증은 오프라인에서, chunk는 명시적 모델 설정으로 동작한다.
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from starter_rag.contracts.models import SearchRequest
from starter_rag.ingestion.chunking import DEFAULT_TARGET_TOKENS, DocumentChunk
from starter_rag.ingestion.chunking_model import (
    ChunkingModelConfigurationError,
    ChunkingModelInitializationError,
)
from starter_rag.ingestion.parser import (
    DocumentReadError,
    DocumentStructure,
    UnsupportedDocumentFormatError,
    extract_document_structure,
    parse_document,
)
from starter_rag.ingestion.service import chunk_document_with_config


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
            "unverified_items": [asdict(item) for item in structure.unverified_items],
        }
        output = json.dumps(payload, ensure_ascii=False)
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 파서 오류는 CLI 사용자에게 표시한다.
        print(f"문서 파싱에 실패했습니다: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("양의 정수를 입력해야 합니다") from None
    if result <= 0:
        raise argparse.ArgumentTypeError("양의 정수를 입력해야 합니다")
    return result


def _load_tokenizer(path: str):
    # 로컬 파일 또는 이미 캐시된 토크나이저만 불러오며 원격으로 내려받지 않는다.
    try:
        from transformers import AutoTokenizer
    except ImportError:
        raise RuntimeError(
            "토크나이저를 불러오려면 RAG의 transformers 의존성이 필요합니다."
        ) from None

    try:
        return AutoTokenizer.from_pretrained(
            path,
            local_files_only=True,
            trust_remote_code=False,
        )
    except Exception:  # noqa: BLE001 - 로컬 캐시 오류에 내부 구현 정보가 포함될 수 있다.
        raise ValueError(
            "로컬 토크나이저를 불러오지 못했습니다. 다운로드된 토크나이저 경로를 확인하세요."
        ) from None


def _chunk_summary(chunk: DocumentChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "kind": chunk.kind,
        "element_ids": chunk.element_ids,
        "text": chunk.text,
        "content_sha256": chunk.content_sha256,
        "locations": [asdict(location) for location in chunk.locations],
        "table_row": asdict(chunk.table_row) if chunk.table_row is not None else None,
        "token_count": chunk.token_count,
        "over_target": chunk.over_target,
        "generation_method": chunk.generation_method,
        "model_status": chunk.model_status,
        "model_attempts": chunk.model_attempts,
        "model_failure": chunk.model_failure,
        "fallback_used": chunk.fallback_used,
    }


def _chunk_file(
    path: str,
    *,
    tokenizer_path: str,
    source_id: str | None,
    version: str,
    target_tokens: int,
) -> int:
    source = Path(path)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            document = parse_document(source)
            structure: DocumentStructure = extract_document_structure(document, source)
            try:
                tokenizer = _load_tokenizer(tokenizer_path)
            except ValueError:
                print("로컬 토크나이저 경로 또는 설정을 확인하세요.", file=sys.stderr)
                return 2

            def count_tokens(text: str) -> int:
                return len(tokenizer.encode(text, add_special_tokens=False))

            try:
                chunks = asyncio.run(
                    chunk_document_with_config(
                        structure,
                        source_id=source_id or source.name,
                        version=version,
                        count_tokens=count_tokens,
                        target_tokens=target_tokens,
                    )
                )
            except (ChunkingModelConfigurationError, ChunkingModelInitializationError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            except ValueError:
                print("RAG 공급자 설정 또는 청킹 입력이 올바르지 않습니다.", file=sys.stderr)
                return 2
        payload = {
            "input_file": path,
            "success": True,
            "source_format": structure.source_format,
            "source_id": source_id or source.name,
            "version": version,
            "tokenizer": Path(tokenizer_path).name,
            "chunk_count": len(chunks),
            "chunks": [_chunk_summary(chunk) for chunk in chunks],
        }
        output = json.dumps(payload, ensure_ascii=False)
    except (FileNotFoundError, UnsupportedDocumentFormatError, DocumentReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError:
        print("문서 청킹 입력이 올바르지 않습니다.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 공급자 인증 정보가 있을 수 있어 예외 원문을 출력하지 않는다.
        print(f"청킹 실행에 실패했습니다: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="starter-rag", description="RAG 계약 확인 및 명시적 청킹 CLI"
    )
    parser.add_argument("--file", type=_file_argument, metavar="PATH")
    cmd = parser.add_subparsers(dest="command", required=False)
    cmd.add_parser("status", help="검색/적재 구현 상태 확인 (DB 연결 없음)")
    validate = cmd.add_parser("validate-search", help="검색 요청 DTO 검증 (DB 연결 없음)")
    validate.add_argument("--query", required=True)
    validate.add_argument("--top-k", type=int, default=3)
    chunk = cmd.add_parser("chunk", help="문서를 청킹해 결과와 모델 상태를 JSON으로 출력")
    chunk.add_argument(
        "--file", dest="chunk_file", type=_file_argument, required=True, metavar="PATH"
    )
    chunk.add_argument(
        "--tokenizer-path",
        required=True,
        metavar="PATH",
        help="로컬 토크나이저 경로 또는 캐시 ID (원격 다운로드 안 함)",
    )
    chunk.add_argument("--source-id")
    chunk.add_argument("--version", default="cli-test")
    chunk.add_argument("--target-tokens", type=_positive_integer, default=DEFAULT_TARGET_TOKENS)
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
    if args.command == "chunk":
        return _chunk_file(
            args.chunk_file,
            tokenizer_path=args.tokenizer_path,
            source_id=args.source_id,
            version=args.version,
            target_tokens=args.target_tokens,
        )
    try:
        req = SearchRequest(query=args.query, top_k=args.top_k)
    except ValueError as exc:
        parser.exit(2, f"잘못된 RAG 검색 요청: {exc}\n")
    print(json.dumps({"valid": True, "query": req.query, "topK": req.top_k}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
