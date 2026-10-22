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
from inheritance.checklist.rules import PROCEDURE_ORDER, PROCEDURE_TITLES
from inheritance.main import create_app

FRONTEND_MOCK = Path(__file__).resolve().parents[1] / "frontend" / "src" / "mocks" / "procedures.ts"
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


def test_static_data_matches_frontend_mock_text():
    # 정민 님 Mock(#74)과 문장이 한 글자라도 달라지면 실패한다.
    source = FRONTEND_MOCK.read_text(encoding="utf-8")
    texts = [s.summary for s in PROCEDURE_SUMMARIES] + [s.name for s in PROCEDURE_SUMMARIES]
    for detail in PROCEDURE_DETAILS.values():
        texts += [detail.action, detail.deadline, detail.risk, detail.agency]
        texts += [*detail.documents, *detail.methods, *detail.exceptions, *detail.contacts]
        texts += [part for link in detail.official_links for part in (link.title, link.url)]
    missing = [text for text in texts if json.dumps(text, ensure_ascii=False) not in source]
    assert missing == []
