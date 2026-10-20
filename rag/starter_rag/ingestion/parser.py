# 담당: [D] | 책임: Docling 기반 공식 안내자료 문서 변환.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-1
# 구현할 기능: 로컬 PDF/DOCX/HTML을 DoclingDocument로 변환하고 실패 유형을 구분한다.
# 완료 기준: Docling 성공 상태의 변환 결과를 반환하고, 입력·변환 실패를 각각 식별한다.
# 제한사항: 명시적으로 호출한 파일만 변환하며 법령 원문을 벡터 색인하지 않는다.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from docling_core.types.doc import DoclingDocument

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".html", ".htm"})


class UnsupportedDocumentFormatError(ValueError):
    """입력 확장자가 Docling 변환 어댑터에서 지원되지 않는다."""


class DocumentReadError(OSError):
    """입력 파일을 확인하거나 읽을 수 없다."""


class DocumentConversionError(RuntimeError):
    """Docling 변환이 실패했거나 성공 문서를 반환하지 않았다."""


def _create_converter() -> DocumentConverter:
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.HTML]
    )


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    return _create_converter()


def _validate_source(source: Path) -> None:
    try:
        source.stat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"문서 파일이 없습니다: {source}") from error
    except OSError as error:
        raise DocumentReadError(f"문서 파일을 확인할 수 없습니다: {source}") from error

    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentFormatError(
            f"지원하지 않는 문서 형식입니다: {source.suffix or '(확장자 없음)'}"
        )

    try:
        with source.open("rb") as document_file:
            document_file.read(1)
    except OSError as error:
        raise DocumentReadError(f"문서 파일을 읽을 수 없습니다: {source}") from error


def parse_document(path: str | Path) -> DoclingDocument:
    source = Path(path)
    _validate_source(source)

    try:
        result = _get_converter().convert(source, raises_on_error=False)
    except Exception as error:
        raise DocumentConversionError(f"Docling 변환에 실패했습니다: {source}") from error

    status = getattr(result.status, "value", result.status)
    # 일부 페이지나 구조만 변환된 결과도 정상 문서로 넘기지 않는다.
    if status != "success":
        raise DocumentConversionError(
            f"Docling 변환 상태가 성공이 아닙니다: {source} ({status})"
        )

    document = getattr(result, "document", None)
    if document is None:
        raise DocumentConversionError(f"Docling 결과에 문서가 없습니다: {source}")
    return document
