# 담당: [통합] | 책임: [통합] 내부 계약의 정의/경계 단위 테스트.
# 구현할 기능: Port/DTO의 입력 불변식과 정상·오류 동작을 계약 테스트로 확인.
# 코드 경계: 외부 서비스 호출/HTTP wire 상세를 이 파일에 구현하지 않는다.
# 완료 기준: Python 3.13 표준 라이브러리 계약 테스트 통과.
"""[통합] 내부 계약의 정의/경계 단위 테스트.
구현할 기능: 공통 8개 절차 안내, LLM DTO, RAG Evidence·문서 상태, 법령/인계 DTO 검증.
완료 기준: Python 3.13 표준 라이브러리로 10개 이상 독립 실행 통과.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import get_args

root = Path(__file__).resolve().parents[1]
for x in ["llm", "rag", "backend/src"]:
    sys.path.insert(0, str(root / x))

from inheritance.contracts.chat import (
    MAX_CLARIFICATION_QUESTIONS,
    MAX_PREVIOUS_MESSAGES,
    MAX_QUESTION_CODEPOINTS,
    AnswerOutcome,
    AnswerStatus,
    ChatInputPolicy,
)
from inheritance.contracts.domain import (
    GuidanceResult,
    InitialAnswers,
    ProcedureGuidance,
    RiskAnswer,
)
from inheritance.contracts.handoff import HandoffExchange, HandoffPayload
from inheritance.contracts.law import LawLookupResult
from starter_llm.contracts.errors import ModelError, ModelErrorCode
from starter_llm.contracts.models import GenerationRequest, ModelMessage
from starter_rag.contracts.models import (
    DocumentVersion,
    Evidence,
    SearchRequest,
    SearchResult,
    SourceRef,
)


class ContractTest(unittest.TestCase):
    def test_valid_generation_request(self):
        q = GenerationRequest((ModelMessage("user", "검증용 합성 질문"),), "gemini", "req-123", 2.0)
        self.assertEqual(q.timeout_seconds, 2.0)  # 합성 시험 입력; 계약 기본값 아님

    def test_empty_llm_request_rejected(self):
        with self.assertRaises(ValueError):
            GenerationRequest((), "gemini", "req-123", 2.0)

    def test_missing_model_request_id_rejected(self):
        with self.assertRaises(ValueError):
            GenerationRequest((ModelMessage("user", "synthetic"),), "gemini", "", 2.0)

    def test_invalid_model_timeout_rejected(self):
        with self.assertRaises(ValueError):
            GenerationRequest((ModelMessage("user", "synthetic"),), "gemini", "id", 0)

    def test_llm_timeout_default_and_ceiling(self):
        req = GenerationRequest((ModelMessage("user", "synthetic"),), "gemini", "id")
        self.assertEqual(req.timeout_seconds, 30.0)
        max_req = GenerationRequest((ModelMessage("user", "synthetic"),), "gemini", "id", 300)
        self.assertEqual(max_req.timeout_seconds, 300)
        with self.assertRaises(ValueError):
            GenerationRequest((ModelMessage("user", "synthetic"),), "gemini", "id", 301)

    def test_rag_topk_default_and_ceiling(self):
        self.assertEqual(SearchRequest("q").top_k, 3)
        self.assertEqual(SearchRequest("q", 10).top_k, 10)
        with self.assertRaises(ValueError):
            SearchRequest("q", 11)

    def test_t5_codepoint_count(self):
        policy = ChatInputPolicy()
        self.assertEqual(
            (MAX_QUESTION_CODEPOINTS, MAX_PREVIOUS_MESSAGES, MAX_CLARIFICATION_QUESTIONS),
            (200, 3, 0),
        )
        policy.validate_question(
            "😀" * 200
        )  # Python len counts astral characters as one code point.
        with self.assertRaises(ValueError):
            policy.validate_question("😀" * 201)
        with self.assertRaises(ValueError):
            policy.validate_question("  ")

    def test_t5_history_and_clarification(self):
        policy = ChatInputPolicy()
        policy.validate_history_count(0)
        policy.validate_history_count(3)
        with self.assertRaises(ValueError):
            policy.validate_history_count(4)
        self.assertNotIn("clarification", get_args(AnswerStatus))
        with self.assertRaises(ValueError):
            ChatInputPolicy(max_question_codepoints=201)

    def test_model_error_never_contains_raw_prompt(self):
        e = ModelError(ModelErrorCode.TIMEOUT, "req-123", True)
        self.assertEqual(str(e), "MODEL_TIMEOUT")

    def test_source_https(self):
        with self.assertRaises(ValueError):
            SourceRef("s", "title", "http://test.test", "agency", "v1")

    def test_source_evidence_complete(self):
        src = SourceRef("s", "title", "https://example.org/test", "agency", "v1")
        ev = Evidence("e", src, "안내 내용", "page:1")
        self.assertEqual(SearchResult((ev,)).evidence[0].location, "page:1")

    def test_empty_search_is_valid(self):
        self.assertEqual(SearchResult(()).evidence, ())

    def test_search_topk(self):
        with self.assertRaises(ValueError):
            SearchRequest("q", 0)

    def test_guidance_result_requires_all_eight_procedures(self):
        rows = tuple(ProcedureGuidance(f"p{i:02d}") for i in range(1, 9))
        guidance = object()
        risk_information = object()
        result = GuidanceResult(rows, guidance, risk_information, "guidance-v1")
        self.assertEqual(len(result.procedures), 8)
        self.assertEqual(
            {procedure.procedure_id for procedure in result.procedures},
            {"p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"},
        )
        self.assertIs(result.guidance, guidance)
        self.assertIs(result.risk_information, risk_information)

    def test_guidance_result_rejects_duplicate_procedure_ids(self):
        rows = [ProcedureGuidance(f"p{i:02d}") for i in range(1, 9)]
        rows[-1] = ProcedureGuidance("p01")
        with self.assertRaises(ValueError):
            GuidanceResult(tuple(rows), None, None, "guidance-v1")

    def test_guidance_result_rejects_missing_procedure_ids(self):
        rows = tuple(ProcedureGuidance(f"p{i:02d}") for i in range(1, 8))
        with self.assertRaises(ValueError):
            GuidanceResult(rows, None, None, "guidance-v1")

    def test_guidance_result_requires_nonempty_content_version(self):
        rows = tuple(ProcedureGuidance(f"p{i:02d}") for i in range(1, 9))
        for content_version in ("", "   ", None):
            with self.subTest(content_version=content_version), self.assertRaises(ValueError):
                GuidanceResult(rows, None, None, content_version)

    def test_unknown_date_matches_null(self):
        InitialAnswers("spouse", None, True, "unknown")
        with self.assertRaises(ValueError):
            InitialAnswers("spouse", None, False, "unknown")

    def test_citation_gate(self):
        with self.assertRaises(ValueError):
            AnswerOutcome("answered", "답변", (), "req1")

    def test_no_abstention_text(self):
        with self.assertRaises(ValueError):
            AnswerOutcome("abstained", "안전 미검증", (), "req2")

    def test_handoff_minimal_payload(self):
        payload = HandoffPayload(InitialAnswers("spouse", None, True, "unknown"))
        self.assertEqual(HandoffExchange("ok", payload).payload.initial.relationship, "spouse")

    def test_law_status_not_guessed(self):
        q = LawLookupResult("unavailable", ())
        self.assertNotEqual(q.status, "verified")

    def test_date_format_must_be_iso(self):
        with self.assertRaises(ValueError):
            InitialAnswers("spouse", "2026/10/18", False, "yes")

    def test_relationship_code_must_be_recognized(self):
        with self.assertRaises(ValueError):
            InitialAnswers("not-a-code", None, True, "unknown")

    def test_risk_answer_choice_must_be_recognized(self):
        with self.assertRaises(ValueError):
            RiskAnswer("debt", "perhaps")

    def test_procedure_id_must_be_p01_to_p08(self):
        with self.assertRaises(ValueError):
            ProcedureGuidance("p09")

    def test_handoff_failure_cannot_include_data(self):
        payload = HandoffPayload(InitialAnswers("spouse", None, True, "yes"))
        with self.assertRaises(ValueError):
            HandoffExchange("invalid_or_expired", payload)

    def test_verified_law_requires_original_source(self):
        with self.assertRaises(ValueError):
            LawLookupResult("verified", ())

    def test_partial_answer_requires_citations(self):
        with self.assertRaises(ValueError):
            AnswerOutcome("partial", "상세 사항", (), "r1")

    def test_document_requires_nonempty_published_version(self):
        source = SourceRef("s1", "기관 안내", "https://example.org/official", "기관", "v1")
        with self.assertRaises(ValueError):
            DocumentVersion(source, "hash", "published", 0)


if __name__ == "__main__":
    unittest.main()
