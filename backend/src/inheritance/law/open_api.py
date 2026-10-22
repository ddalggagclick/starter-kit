# 담당: [B] | 책임: 법제처 OPEN API로 관련 부칙 전문을 조회한다.
# PRD: E6 / 스토리 6-3 / 태스크 6-3-2.
# 구현할 기능: MCP가 반환한 조문 식별 정보에 연결된 부칙 전문과 공식 URL을 제공한다.
# 완료 기준: 해당 조문의 부칙 전문을 반환하고 시행본이 불일치하거나 조회되지 않으면 미확인으로 처리한다.
# 제한사항: MCP가 반환하지 않은 개정 법률 후보를 자동 탐색하지 않는다. 법령 원문을 RAG에 저장하지 않는다.
# 상태: PRD 태스크 미시작. API 상세는 공식 OPEN API 계약에 따라 구현한다.
"""법제처 OPEN API 부칙 전문 조회 계약.

조회 계약은 addenda_contract.AddendumOpenApiPort(fetch_full_addendum)를 그대로 쓴다.
실제 OPEN API 연결(인증값 OC 환경 변수 이름, 요청 형식)은 정해지지 않아 여기서는 결과 구분만 둔다.
"""

from __future__ import annotations

from inheritance.law.addenda_contract import AddendumOpenApiPort, AmendmentCandidate, FullAddendum
from inheritance.law.mcp_client import LawSourceUnavailable

__all__ = [
    "AddendumNotFound",
    "AddendumOpenApiPort",
    "AmendmentCandidate",
    "FullAddendum",
    "LawSourceUnavailable",
]


class AddendumNotFound(Exception):
    """요청한 시행본(MST·공포번호)의 부칙 전문이 없음. 장애가 아니라 미확인(S7)이다."""
