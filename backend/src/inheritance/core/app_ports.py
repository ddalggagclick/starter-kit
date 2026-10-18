# 담당: [통합] | 책임: 앱 조립에 필요한 서비스 Port 식별.
# PRD: E7 / 스토리 7-1 / 태스크 7-1-4
# 구현할 기능: ModelPort, SearchPort, LawPort, ChecklistService 조립 경계를 제공한다.
# 완료 기준: 라우터에 필요한 구현체를 의존성 주입으로 전달할 수 있다.
# 제한사항: 실제 SDK 연결, DB 구현, 라우트와 도메인 처리를 추가하지 않는다.
"""I19 인스턴스 조립 인터페이스. create_app 구현은 통합 관리자 PR에서 수행."""

from __future__ import annotations

from typing import Protocol

from starter_llm.contracts.ports import ModelPort
from starter_rag.contracts.ports import SearchPort

from inheritance.contracts.checklist import ChecklistService
from inheritance.contracts.law import LawPort


class AppServicePorts(Protocol):
    model: ModelPort
    search: SearchPort
    law: LawPort
    checklist: ChecklistService
