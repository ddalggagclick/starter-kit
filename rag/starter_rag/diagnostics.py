# 담당: [D] | 책임: 관리자 CLI의 비밀정보 없는 오류 진단.
# 구현할 기능: DB·Ollama·컨텍스트·임베딩·파서·HITL·게시 오류를 구분한다.
# 완료 기준: 원시 예외 문자열·연결 정보·토큰을 출력하지 않는다.
from __future__ import annotations

from sqlalchemy.exc import DBAPIError, OperationalError

from starter_rag.embedding.model import EmbeddingError
from starter_rag.ingestion.chunking import ChunkingError
from starter_rag.ingestion.chunking_model import (
    ChunkingModelConfigurationError,
    ChunkingModelInitializationError,
)
from starter_rag.ingestion.parser import DocumentConversionError, DocumentReadError
from starter_rag.ingestion.review import ReviewError
from starter_rag.storage.database import DatabaseConfigurationError, DatabaseSchemaError
from starter_rag.storage.publication import PublicationError
from starter_rag.storage.vector_store import VectorStoreError


def diagnose(error: BaseException, operation: str) -> str:
    """Return fixed wording; inspect exception text only for a context-limit signal."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and len(chain) < 6:
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(item, DatabaseConfigurationError) for item in chain):
        return "DB 설정 오류: config validate로 로컬 DB 이름과 연결 문자열을 확인하세요."
    if any(isinstance(item, DatabaseSchemaError) for item in chain):
        return "DB 미초기화: 격리된 로컬 테스트 DB에서 db-init을 실행하세요."
    if any(isinstance(item, OperationalError) for item in chain):
        return "DB 연결 실패: PostgreSQL 실행 상태와 로컬 DB 설정을 확인하세요."
    if any(isinstance(item, DBAPIError) for item in chain):
        return "SQL 실행 실패: 테이블 스키마와 DB 권한을 확인하세요."
    if any(isinstance(item, ReviewError) for item in chain):
        return "HITL 승인 오류: review validate 후 원본과 대조하고 다시 승인하세요."
    if any(isinstance(item, EmbeddingError) for item in chain):
        return "임베딩 모델 오류: 승인된 로컬 모델 revision과 캐시를 확인하세요."
    if any(isinstance(item, ChunkingModelConfigurationError) for item in chain):
        return "Ollama 모델 설정 오류: config show에서 공급자·모델·컨텍스트 값을 확인하세요."
    if any(isinstance(item, ChunkingModelInitializationError) for item in chain):
        return "Ollama 모델 미실행: ollama serve와 RAG_CHUNKING_MODEL 이름을 확인하세요."
    if any(isinstance(item, (DocumentReadError, DocumentConversionError)) for item in chain):
        return "PDF 파싱 오류: 원본 파일과 Docling 모델 상태를 확인하세요."
    if any(isinstance(item, PublicationError) for item in chain):
        return "게시 오류: 색인 상태, Collection, HITL 승인 해시를 확인하세요."
    if any(isinstance(item, VectorStoreError) for item in chain):
        return "색인 오류: 문서 버전, 청크 ID, 임베딩 차원을 확인하세요."
    if any(
        "context length" in str(item).lower()
        or "context window" in str(item).lower()
        or "num_ctx" in str(item).lower()
        for item in chain
    ):
        return "LLM 컨텍스트 초과: RAG_CHUNKING_CONTEXT_TOKENS와 응답 예산을 조정하세요."
    if (
        any(
            type(item).__name__
            in {"ConnectError", "ConnectionError", "ReadTimeout", "ConnectTimeout"}
            for item in chain
        )
        and operation == "chunk"
    ):
        return "Ollama 연결 실패: ollama serve와 RAG_CHUNKING_MODEL 실행 상태를 확인하세요."
    if any(isinstance(item, ChunkingError) for item in chain):
        return "청킹 오류: 토크나이저, 모델 응답 및 원문 보존 검증 결과를 확인하세요."
    return f"{operation} 실패: {type(error).__name__}. 비밀정보를 제외한 로그와 설정을 확인하세요."
