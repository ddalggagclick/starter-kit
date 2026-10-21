# 담당: [D] | 책임: 문서 파싱·청크·임베딩·적재 유스케이스.
# PRD: E6 / 스토리 6-1 / 태스크 6-1-2, 6-1-3 (임베딩·저장 지원)
# 구현할 기능: 문서 버전별 적재를 수행하고 실패 상태를 기록한다.
# 완료 기준: 검수·게시 전 자료가 검색 결과에 노출되지 않는다.
# 제한사항: 적재는 관리자 실행으로 제한하고 앱 시작 때 자동 실행하지 않는다.
from __future__ import annotations

from collections.abc import Callable, Mapping

from langchain_core.language_models.chat_models import BaseChatModel

from starter_rag.ingestion.chunking import (
    DEFAULT_TARGET_TOKENS,
    DocumentChunk,
    chunk_document,
)
from starter_rag.ingestion.chunking_model import create_chunking_model_from_environment
from starter_rag.ingestion.parser import DocumentStructure


async def chunk_document_with_config(
    structure: DocumentStructure,
    *,
    source_id: str,
    version: str,
    count_tokens: Callable[[str], int],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    environ: Mapping[str, str] | None = None,
    model_factory: Callable[[Mapping[str, str] | None], BaseChatModel] | None = None,
) -> tuple[DocumentChunk, ...]:
    configured_model_factory = model_factory or create_chunking_model_from_environment
    model = configured_model_factory(environ)
    return await chunk_document(
        structure,
        source_id=source_id,
        version=version,
        model=model,
        count_tokens=count_tokens,
        target_tokens=target_tokens,
    )
