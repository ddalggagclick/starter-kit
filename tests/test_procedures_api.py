# 담당: [B] 제안 · 배치 승인: [통합] | 책임: A07 절차 목록·상세 API 시험.
# 근거: openapi.yaml A07_listProcedures·A07_getProcedure, D5·D6, W-04 원고(#74).
# 구현할 기능: 8개 고정 목록·순서·이름, 상세 필드, 없는 절차 ID 422, 프론트 Mock과 문장 일치를 확인.
# 완료 기준: 외부 서비스 없이 통과.
"""A07 절차 API 계약 시험. 외부 서비스를 호출하지 않는다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inheritance.checklist.procedures import PROCEDURE_DETAILS, PROCEDURE_SUMMARIES
from inheritance.checklist.rules import CONTENT_VERSION, PROCEDURE_ORDER, PROCEDURE_TITLES
from inheritance.checklist.service import RuleChecklistService
from inheritance.contracts.checklist import GuidanceInput
from inheritance.contracts.domain import InitialAnswers
from inheritance.main import create_app

FRONTEND_PROCEDURES = (
    Path(__file__).resolve().parents[1] / "frontend/src/shared/content/procedures.ts"
)
DETAIL_KEYS = {
    "procedureId",
    "action",
    "deadline",
    "risk",
    "agency",
    "documents",
    "methods",
    "exceptions",
    "contacts",
    "officialLinks",
    "relatedProcedureIds",
    "contentVersion",
}


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_list_returns_eight_procedures_in_fixed_order(client):
    response = client.get("/api/procedures")
    assert response.status_code == 200
    procedures = response.json()["procedures"]
    assert [p["procedureId"] for p in procedures] == list(PROCEDURE_ORDER)
    assert [p["name"] for p in procedures] == [PROCEDURE_TITLES[pid] for pid in PROCEDURE_ORDER]
    assert all(set(p) == {"procedureId", "name", "summary"} and p["summary"] for p in procedures)
    assert response.json()["contentVersion"] == CONTENT_VERSION


@pytest.mark.parametrize("procedure_id", PROCEDURE_ORDER)
def test_detail_returns_camel_case_fields(client, procedure_id):
    response = client.get(f"/api/procedures/{procedure_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert body["procedureId"] == procedure_id
    assert all(body[key] for key in ("action", "deadline", "risk", "agency"))
    assert all(
        link["url"].startswith("https://") and link["title"] for link in body["officialLinks"]
    )
    # D4 보류: 함께 보면 좋은 절차는 아직 비운다.
    assert body["relatedProcedureIds"] == []


@pytest.mark.parametrize("procedure_id", ["p00", "p09", "P01", "1"])
def test_unknown_procedure_id_is_validation_error(client, procedure_id):
    response = client.get(f"/api/procedures/{procedure_id}")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_static_data_matches_frontend_procedure_text():
    # 정민 님 화면 원고(#74, #187에서 shared/content로 이동)와 문장이 한 글자라도 달라지면 실패한다.
    source = FRONTEND_PROCEDURES.read_text(encoding="utf-8")
    texts = [s.summary for s in PROCEDURE_SUMMARIES] + [s.name for s in PROCEDURE_SUMMARIES]
    for detail in PROCEDURE_DETAILS.values():
        texts += [detail.action, detail.deadline, detail.risk, detail.agency]
        texts += [*detail.documents, *detail.methods, *detail.exceptions, *detail.contacts]
        texts += [part for link in detail.official_links for part in (link.title, link.url)]
    missing = [text for text in texts if json.dumps(text, ensure_ascii=False) not in source]
    assert missing == []


# ---- 2-2-2: 카카오(체크리스트 규칙)와 웹(A07)이 같은 콘텐츠 버전·8개 절차·공식 출처를 쓴다 ----------


def _kakao_guidance():
    initial = InitialAnswers(
        relationship="spouse",
        death_date=None,
        death_date_unknown=True,
        one_stop_application="unknown",
    )
    return RuleChecklistService().build_guidance(GuidanceInput(initial))


def test_kakao_and_web_share_content_version_and_procedures(client):
    kakao = _kakao_guidance()
    web_list = client.get("/api/procedures").json()
    assert web_list["contentVersion"] == kakao.content_version == CONTENT_VERSION
    assert [p["procedureId"] for p in web_list["procedures"]] == [
        g.procedure_id for g in kakao.guidance
    ]
    assert [p["name"] for p in web_list["procedures"]] == [g.title for g in kakao.guidance]
    for procedure_id in PROCEDURE_ORDER:
        detail = client.get(f"/api/procedures/{procedure_id}").json()
        assert detail["contentVersion"] == kakao.content_version


# 연결할 공식 안내 페이지가 없다고 팀이 확인한 절차. 지금은 없다(p02는 2026-10-26 웹 링크 확인).
# 확인되지 않은 링크를 지어내지 않는다. 출처가 확정되면 이 목록에서 빼고 링크를 넣는다(PRD 1-3-2).
KNOWN_SOURCE_GAPS: set[str] = set()


def test_every_procedure_has_official_https_source_on_kakao_or_web(client):
    kakao = {g.procedure_id: g for g in _kakao_guidance().guidance}
    without_source = set()
    for procedure_id in PROCEDURE_ORDER:
        web_links = client.get(f"/api/procedures/{procedure_id}").json()["officialLinks"]
        fallback = kakao[procedure_id].fallback
        kakao_links = list(fallback.links) if fallback else []
        urls = [link["url"] for link in web_links] + [link.url for link in kakao_links]
        if not urls:
            without_source.add(procedure_id)
        assert all(url.startswith("https://") for url in urls)
        assert all(link.browser_checked for link in kakao_links)
    # 알려진 빈칸만 허용한다. 다른 절차의 출처가 사라지면 실패한다.
    assert without_source == KNOWN_SOURCE_GAPS
