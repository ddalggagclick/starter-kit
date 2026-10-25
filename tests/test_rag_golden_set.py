# Golden Set 검증 및 오프라인 검색 지표 테스트.

from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from starter_rag.contracts.models import Evidence, SearchRequest, SearchResult, SourceRef
from starter_rag.evaluation.golden_set import (
    GoldenSearchCommandError,
    GoldenSetValidationError,
    _ranked_relevance_metrics,
    _same_url,
    evaluate_golden_set,
    evaluate_source_v2_golden,
    load_golden_set,
    parse_golden_set,
    validate_chunk_mapping,
    validate_chunk_mappings,
)

SYNTHETIC_LOCATION_1 = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"1"}]}]'
)
SYNTHETIC_LOCATION_2 = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"2"}]}]'
)
SYNTHETIC_LOCATION_7 = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"7"}]}]'
)
SYNTHETIC_LOCATION_8 = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"8"}]}]'
)
SYNTHETIC_LOCATION_9 = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"9"}]}]'
)
SYNTHETIC_ADJACENT_LOCATION = (
    '[{"status":"not_applicable","page_numbers":[],"provenance":[{"test_location":"1-adjacent"}]}]'
)


class FixedSearchPort:
    def __init__(self, results_by_query: dict[str, tuple[Evidence, ...]]) -> None:
        self.results_by_query = results_by_query
        self.requests: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> SearchResult:
        self.requests.append(request)
        return SearchResult(self.results_by_query.get(request.query, ()))


class SourceV2EvaluationCliTests(unittest.TestCase):
    def test_검색_CLI_오류_종료_코드를_평가_명령에_전달한다(self) -> None:
        dataset = Path(__file__).resolve().parents[1] / "rag/evaluation/source_v2_golden_v1_2.json"
        for search_exit_code, expected_exit_code in ((2, 2), (1, 1)):
            with tempfile.TemporaryDirectory() as directory:
                stderr = StringIO()
                with (
                    patch.dict(os.environ, {"RAG_DATABASE_URL": "configured"}, clear=True),
                    patch(
                        "starter_rag.evaluation.golden_set._search_source_v2_golden",
                        side_effect=GoldenSearchCommandError(search_exit_code),
                    ),
                    redirect_stderr(stderr),
                ):
                    exit_code = evaluate_source_v2_golden(
                        dataset_path=dataset,
                        out_path=Path(directory) / "result.json",
                    )

            self.assertEqual(exit_code, expected_exit_code)
            self.assertIn("RAG search failed", stderr.getvalue())

    def test_평가_결과는_기본_표준출력으로_출력하고_지정한_경로에만_저장한다(self) -> None:
        dataset = Path(__file__).resolve().parents[1] / "rag/evaluation/source_v2_golden_v1_2.json"

        def evaluate(question, _mode):
            return {
                "query_id": question["query_id"],
                "group": question["group"],
                "first_relevant_rank": 1,
                "hit_at_3": 1,
                "hit_at_10": 1,
                "recall_at_3": 1.0,
                "recall_at_10": 1.0,
                "mrr_at_3": 1.0,
                "mrr_at_10": 1.0,
            }

        stdout = StringIO()
        with (
            patch.dict(os.environ, {"RAG_DATABASE_URL": "configured"}, clear=True),
            patch(
                "starter_rag.evaluation.golden_set._evaluate_source_v2_query", side_effect=evaluate
            ),
            patch.object(
                Path, "mkdir", side_effect=AssertionError("unexpected directory creation")
            ) as mkdir,
            patch.object(
                Path, "write_text", side_effect=AssertionError("unexpected result file")
            ) as write_text,
            redirect_stdout(stdout),
        ):
            self.assertEqual(evaluate_source_v2_golden(dataset_path=dataset), 0)
        mkdir.assert_not_called()
        write_text.assert_not_called()
        self.assertIn("OVERALL:", stdout.getvalue())
        self.assertIn("BY GROUP:", stdout.getvalue())
        self.assertNotIn("RESULT:", stdout.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "evaluation.json"
            stdout = StringIO()
            with (
                patch.dict(os.environ, {"RAG_DATABASE_URL": "configured"}, clear=True),
                patch(
                    "starter_rag.evaluation.golden_set._evaluate_source_v2_query",
                    side_effect=evaluate,
                ),
                redirect_stdout(stdout),
            ):
                self.assertEqual(
                    evaluate_source_v2_golden(dataset_path=dataset, out_path=output), 0
                )
            self.assertEqual(
                json.loads(output.read_text())["status"], "measured_retrieval_relevance_only"
            )
            self.assertIn(f"RESULT: {output}", stdout.getvalue())


def _retrieved_evidence(
    evidence_id: str,
    *,
    location: str = SYNTHETIC_LOCATION_1,
    official_url: str = "https://official.example.gov/page",
    version: str = "2026-01-01",
    source_id: str = "synthetic-source",
    title: str = "합성 테스트 자료",
    publisher: str = "합성 테스트 기관",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source=SourceRef(
            source_id=source_id,
            title=title,
            url=official_url,
            publisher=publisher,
            version=version,
        ),
        text="합성 평가 근거",
        location=location,
    )


def _valid_dataset() -> dict[str, object]:
    return {
        "dataset_version": "test-v1",
        "dataset_type": "synthetic_test",
        "label_level": "document_location",
        "scope": "합성 입력만 사용하는 단위 테스트",
        "rag_publication_status": "unconfirmed",
        "search_snapshot_version": None,
        "queries": [
            {
                "query_id": "q-1",
                "question": "첫 번째 위치의 내용을 알려줘.",
                "question_type": "direct",
                "verification_status": "verified",
                "relevant_evidence": [
                    {
                        "source_id": "synthetic-source",
                        "source_title": "합성 테스트 자료",
                        "publisher": "합성 테스트 기관",
                        "version": "2026-01-01",
                        "evidence_id": None,
                        "location": "§ 1",
                        "location_mapping_status": "mapped",
                        "location_match_key": SYNTHETIC_LOCATION_1,
                        "official_url": "https://official.example.gov/page",
                    },
                    {
                        "source_id": "synthetic-source",
                        "source_title": "합성 테스트 자료",
                        "publisher": "합성 테스트 기관",
                        "version": "2026-01-01",
                        "evidence_id": None,
                        "location": "§ 2",
                        "location_mapping_status": "mapped",
                        "location_match_key": SYNTHETIC_LOCATION_2,
                        "official_url": "https://official.example.gov/page",
                    },
                ],
            },
            {
                "query_id": "q-no-answer",
                "question": "이 문서 범위에 없는 내용을 알려줘.",
                "question_type": "no_answer",
                "verification_status": "verified_no_answer",
                "relevant_evidence": [],
                "verification_note": "합성 자료에 답변 근거가 없는 테스트 사례.",
            },
        ],
    }


def _valid_chunk_dataset() -> dict[str, object]:
    payload = _valid_dataset()
    payload["label_level"] = "chunk"  # type: ignore[index]
    payload["collection_id"] = "rag-test-unit"  # type: ignore[index]
    for label_index, label in enumerate(
        payload["queries"][0]["relevant_evidence"]  # type: ignore[index]
    ):
        label["evidence_id"] = f"synthetic-chunk-{label_index + 1}"
        label["location_mapping_status"] = "mapped"
        label["supporting_text"] = "합성 평가 근거"
        label["location_match_key"] = SYNTHETIC_LOCATION_1
    return payload


def _chunk_record(evidence_id: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "chunk_id": evidence_id,
        "source_id": "synthetic-source",
        "source_title": "합성 테스트 자료",
        "publisher": "합성 테스트 기관",
        "version": "2026-01-01",
        "source_url": "https://official.example.gov/page",
        "publication_state": "published",
        "collection_id": "rag-test-unit",
        "is_synthetic": True,
        "content": "앞 문장. 합성 평가 근거. 뒤 문장.",
        "location": SYNTHETIC_LOCATION_1,
    }
    record.update(overrides)
    return record


class GoldenSetValidationTests(unittest.TestCase):
    def test_순위_지표는_중복_결과에서_정답_라벨을_한번만_센다(self) -> None:
        metrics = _ranked_relevance_metrics([{0}, {0}, {1}], 2, (1, 2, 3))

        self.assertEqual(metrics[1], {"recall": 0.5, "mrr": 1.0, "complete": False})
        self.assertEqual(metrics[2], {"recall": 0.5, "mrr": 1.0, "complete": False})
        self.assertEqual(metrics[3], {"recall": 1.0, "mrr": 1.0, "complete": True})

    def test_json_파일에서_데이터셋을_불러온다(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "golden_set.json"
            dataset_path.write_text(
                json.dumps(_valid_dataset(), ensure_ascii=False), encoding="utf-8"
            )

            dataset = load_golden_set(dataset_path)

        self.assertEqual(dataset.dataset_version, "test-v1")
        self.assertEqual(dataset.label_level, "document_location")
        self.assertEqual(len(dataset.queries), 2)

    def test_중복_질문_id를_거부한다(self) -> None:
        payload = _valid_dataset()
        payload["queries"] = [payload["queries"][0], payload["queries"][0]]  # type: ignore[index]

        with self.assertRaisesRegex(GoldenSetValidationError, "q-1"):
            parse_golden_set(payload)

    def test_출처나_위치가_없는_검증_근거를_거부한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][0]["location"] = ""  # type: ignore[index]

        with self.assertRaisesRegex(GoldenSetValidationError, "q-1"):
            parse_golden_set(payload)

    def test_https가_아닌_공식_url을_거부한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][0]["official_url"] = "http://official.example.gov/page"  # type: ignore[index]

        with self.assertRaisesRegex(GoldenSetValidationError, "q-1"):
            parse_golden_set(payload)

    def test_미확인_버전이나_위치를_검증된_라벨로_표시하는_입력을_거부한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][0]["version"] = "미확인"  # type: ignore[index]

        with self.assertRaisesRegex(GoldenSetValidationError, "version"):
            parse_golden_set(payload)

        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][0]["location"] = "확인 필요"  # type: ignore[index]
        with self.assertRaisesRegex(GoldenSetValidationError, "location"):
            parse_golden_set(payload)

    def test_잘못된_질문_유형과_중복_라벨을_거부한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["question_type"] = "guessing"  # type: ignore[index]

        with self.assertRaisesRegex(GoldenSetValidationError, "question_type"):
            parse_golden_set(payload)

        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][1]["location"] = query["relevant_evidence"][0]["location"]  # type: ignore[index]
        query["relevant_evidence"][1]["source_id"] = "mapped-synthetic-source"  # type: ignore[index]
        with self.assertRaisesRegex(GoldenSetValidationError, "duplicate"):
            parse_golden_set(payload)

    def test_라벨_수준_혼합과_미검증_라벨_평가를_거부한다(self) -> None:
        payload = _valid_dataset()
        payload["label_level"] = "chunk"  # type: ignore[index]
        payload["collection_id"] = "rag-test-unit"  # type: ignore[index]
        query = payload["queries"][0]  # type: ignore[index]
        for label in query["relevant_evidence"]:  # type: ignore[index]
            label.pop("location_mapping_status")
            label.pop("location_match_key")
        query["relevant_evidence"][0]["evidence_id"] = "chunk-1"  # type: ignore[index]
        with self.assertRaisesRegex(GoldenSetValidationError, "supporting_text"):
            parse_golden_set(payload)

        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["verification_status"] = "unverified"  # type: ignore[index]
        query["relevant_evidence"] = []  # type: ignore[index]
        query["exclusion_reason"] = "문서 버전 확인 대기"  # type: ignore[index]
        dataset = parse_golden_set(payload)
        self.assertEqual(dataset.queries[0].verification_status, "unverified")


class GoldenSetChunkMappingTests(unittest.TestCase):
    def test_선언된_컬렉션의_게시_청크_매핑을_허용한다(self) -> None:
        dataset = parse_golden_set(_valid_chunk_dataset())
        labels = dataset.queries[0].relevant_evidence
        records = {
            label.evidence_id: _chunk_record(label.evidence_id)
            for label in labels
            if label.evidence_id is not None
        }

        self.assertEqual(validate_chunk_mappings(dataset, records), 2)
        validate_chunk_mapping(
            labels[0],
            records[labels[0].evidence_id],
            expected_collection_id=dataset.collection_id or "",
            expected_is_synthetic=True,
        )

    def test_존재하지_않는_청크_id_매핑을_거부한다(self) -> None:
        dataset = parse_golden_set(_valid_chunk_dataset())
        first_id = dataset.queries[0].relevant_evidence[0].evidence_id

        with self.assertRaisesRegex(GoldenSetValidationError, "does not exist"):
            validate_chunk_mappings(dataset, {"different-id": _chunk_record("different-id")})

        self.assertIsNotNone(first_id)

    def test_출처_버전_url_또는_게시_상태가_다른_청크_매핑을_거부한다(self) -> None:
        dataset = parse_golden_set(_valid_chunk_dataset())
        label = dataset.queries[0].relevant_evidence[0]
        assert label.evidence_id is not None
        invalid_records = (
            _chunk_record(label.evidence_id, source_id="other-source"),
            _chunk_record(label.evidence_id, version="2025-01-01"),
            _chunk_record(label.evidence_id, source_url="https://other.gov/page"),
            _chunk_record(label.evidence_id, publication_state="staging"),
            _chunk_record(label.evidence_id, collection_id="staging-guides"),
            _chunk_record(label.evidence_id, is_synthetic=False),
            _chunk_record(label.evidence_id, location=SYNTHETIC_LOCATION_2),
        )

        for record in invalid_records:
            with self.subTest(record=record), self.assertRaises(GoldenSetValidationError):
                validate_chunk_mapping(
                    label,
                    record,
                    expected_collection_id=dataset.collection_id or "",
                    expected_is_synthetic=True,
                )

    def test_정답_문구가_없는_청크를_거부한다(self) -> None:
        dataset = parse_golden_set(_valid_chunk_dataset())
        label = dataset.queries[0].relevant_evidence[0]
        assert label.evidence_id is not None

        with self.assertRaisesRegex(GoldenSetValidationError, "does not contain"):
            validate_chunk_mapping(
                label,
                _chunk_record(label.evidence_id, content="인접 문단에는 다른 내용만 있습니다."),
                expected_collection_id=dataset.collection_id or "",
                expected_is_synthetic=True,
            )


class GoldenSetUrlMatchingTests(unittest.TestCase):
    def test_fsc_탐색_매개변수와_경로_별칭만_무시한다(self) -> None:
        stable_url = "https://fsc.go.kr/po010104/87657"
        listing_url = (
            "https://fsc.go.kr/po010104/87657"
            "?curPage=9&srchBeginDt=&srchCtgry=&srchEndDt=&srchKey=&srchText="
        )

        self.assertTrue(_same_url(stable_url, listing_url))
        self.assertTrue(_same_url(stable_url, "https://www.fsc.go.kr/po010101/87657?curPage=4"))
        self.assertFalse(_same_url(stable_url, stable_url + "?view=print"))
        self.assertFalse(
            _same_url(
                "https://fsc.go.kr/po010104/87658?curPage=9",
                "https://fsc.go.kr/po010104/87658",
            )
        )
        self.assertFalse(
            _same_url("https://example.gov/article?curPage=9", "https://example.gov/article")
        )


class GoldenSetMetricTests(unittest.IsolatedAsyncioTestCase):
    async def test_위치_라벨로_recall과_mrr을_계산하고_중복_검색을_무시한다(
        self,
    ) -> None:
        payload = _valid_dataset()
        payload["queries"] = [payload["queries"][0]]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("same-location-a", location=SYNTHETIC_LOCATION_1),
                    _retrieved_evidence("same-location-b", location=SYNTHETIC_LOCATION_1),
                    _retrieved_evidence("other", location=SYNTHETIC_LOCATION_9),
                    _retrieved_evidence("second-answer", location=SYNTHETIC_LOCATION_2),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 0.5)
        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 1.0)
        self.assertEqual(port.requests, [SearchRequest("첫 번째 위치의 내용을 알려줘.", top_k=10)])
        self.assertEqual(summary["label_level"], "document_location")
        self.assertEqual(
            summary["retrieval_policy"],
            "one_top_k_10_request_per_complete_answer_query; @3_uses_first_3_from_same_response; incomplete_questions_excluded",
        )
        self.assertEqual(
            summary["label_match_policy"],
            "source_id_and_exact_official_url_version_structured_location",
        )

    async def test_fsc_목록_매개변수가_공식_위치_매칭을_깨뜨리지_않는다(self) -> None:
        payload = _valid_dataset()
        payload["queries"] = [payload["queries"][0]]  # type: ignore[index]
        payload["queries"][0]["relevant_evidence"] = payload["queries"][0]["relevant_evidence"][:1]  # type: ignore[index]
        payload["queries"][0]["relevant_evidence"][0]["official_url"] = (  # type: ignore[index]
            "https://fsc.go.kr/po010104/87657"
        )
        dataset = parse_golden_set(payload)
        query = dataset.queries[0]
        label = query.relevant_evidence[0]
        listing_url = (
            "https://fsc.go.kr/po010104/87657"
            "?curPage=9&srchBeginDt=&srchCtgry=&srchEndDt=&srchKey=&srchText="
        )
        port = FixedSearchPort(
            {
                query.question: (
                    _retrieved_evidence(
                        "synthetic-fsc-url-hit",
                        location=SYNTHETIC_LOCATION_1,
                        official_url=listing_url,
                        version=label.version,
                    ),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 1.0)
        self.assertEqual(port.requests[0].top_k, 10)

    async def test_사람용_위치_설명과_json_위치_키를_분리해_매칭한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        query["relevant_evidence"][0]["location"] = "본문 ③ 첫 문단"  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                query["question"]: (
                    _retrieved_evidence("json-location-hit", location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 1.0)
        self.assertEqual(dataset.queries[0].relevant_evidence[0].location, "본문 ③ 첫 문단")

    async def test_구조화_위치_json의_공백_차이를_같은_위치로_처리한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        query["relevant_evidence"][0]["location"] = "본문 ③ 첫 문단"  # type: ignore[index]
        query["relevant_evidence"][0]["location_match_key"] = json.dumps(
            json.loads(SYNTHETIC_LOCATION_1), ensure_ascii=False, indent=2, sort_keys=True
        )  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                query["question"]: (
                    _retrieved_evidence("canonical-json-hit", location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)

    async def test_미매핑_라벨을_0점으로_계산하지_않고_평가를_막는다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        for label in query["relevant_evidence"]:  # type: ignore[index]
            label["location_mapping_status"] = "unmapped"
            label["location_match_key"] = None
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {"첫 번째 위치의 내용을 알려줘.": (_retrieved_evidence("possible-hit"),)}
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["evaluation_status"], "blocked_unmapped_labels")
        self.assertEqual(summary["evaluated_query_count"], 0)
        self.assertEqual(summary["unmapped_label_count"], 2)
        self.assertIsNone(summary["metrics"]["recall_at_10"])
        self.assertIsNone(summary["result_return_rate"])
        self.assertEqual(port.requests, [])

    async def test_부분_매핑_질문을_recall_분모에서_제외한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][1]["location_mapping_status"] = "unmapped"  # type: ignore[index]
        query["relevant_evidence"][1]["location_match_key"] = None  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("mapped-hit", location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["evaluation_status"], "blocked_unmapped_labels")
        self.assertIsNone(summary["metrics"]["recall_at_10"])
        self.assertEqual(summary["evaluated_query_count"], 0)
        self.assertEqual(summary["mapped_relevant_label_count"], 1)
        self.assertEqual(summary["unmapped_label_count"], 1)
        self.assertEqual(summary["partially_mapped_query_count"], 1)
        self.assertEqual(port.requests, [])

    async def test_인접한_구조화_위치를_정답으로_인정하지_않는다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        query["relevant_evidence"][0]["location"] = "본문 요약 두 번째 항목"  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("adjacent-hit", location=SYNTHETIC_ADJACENT_LOCATION),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_10"], 0.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 0.0)

    def test_구조화_json_키가_없는_매핑_위치를_거부한다(self) -> None:
        payload = _valid_dataset()
        payload["queries"][0]["relevant_evidence"][0]["location_match_key"] = (  # type: ignore[index]
            "본문 ③ 첫 문단"
        )

        with self.assertRaisesRegex(GoldenSetValidationError, "structured JSON"):
            parse_golden_set(payload)

    def test_미매핑_라벨의_위치_키를_거부한다(self) -> None:
        payload = _valid_dataset()
        label = payload["queries"][0]["relevant_evidence"][0]  # type: ignore[index]
        label["location_mapping_status"] = "unmapped"

        with self.assertRaisesRegex(GoldenSetValidationError, "must be null"):
            parse_golden_set(payload)

    async def test_문서_위치_라벨은_문서_id_버전과_정확한_위치를_요구한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        query["relevant_evidence"][0]["source_id"] = "synthetic-source"  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("broader-location", location=SYNTHETIC_ADJACENT_LOCATION),
                    _retrieved_evidence("wrong-version", version="2026-02-01"),
                    _retrieved_evidence(
                        "wrong-document",
                        official_url="https://official.example.gov/other-page",
                    ),
                    _retrieved_evidence("exact-match", location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 0.0)
        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 0.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 0.25)
        self.assertEqual(port.requests, [SearchRequest("첫 번째 위치의 내용을 알려줘.", top_k=10)])

    async def test_첫_정답_순위로_mrr을_계산하고_빈_결과를_0점으로_처리한다(self) -> None:
        payload = _valid_dataset()
        payload["queries"] = [payload["queries"][0]]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("noise-1", location=SYNTHETIC_LOCATION_7),
                    _retrieved_evidence("noise-2", location=SYNTHETIC_LOCATION_8),
                    _retrieved_evidence("answer", location=SYNTHETIC_LOCATION_2),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 0.5)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 0.3333)

        empty_port = FixedSearchPort({})
        empty_summary = await evaluate_golden_set(empty_port, dataset, evaluation_mode="offline")
        self.assertEqual(empty_summary["metrics"]["recall_at_3"], 0.0)
        self.assertEqual(empty_summary["metrics"]["mrr_at_10"], 0.0)

    async def test_정답_없는_질문을_recall과_mrr에서_별도_집계한다(self) -> None:
        dataset = parse_golden_set(_valid_dataset())
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("hit", location=SYNTHETIC_LOCATION_1),
                ),
                "이 문서 범위에 없는 내용을 알려줘.": (_retrieved_evidence("other"),),
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["query_count"], 2)
        self.assertEqual(summary["evaluated_query_count"], 1)
        self.assertEqual(summary["no_answer_query_count"], 1)
        self.assertEqual(summary["returned_result_query_count"], 2)
        self.assertEqual(summary["result_return_rate"], 1.0)
        self.assertEqual(summary["metrics"]["recall_at_10"], 0.5)

    async def test_오프라인과_실제_평가의_데이터_요건을_검증한다(
        self,
    ) -> None:
        dataset = parse_golden_set(_valid_dataset())
        port = FixedSearchPort({})

        offline_summary = await evaluate_golden_set(
            port,
            dataset,
            evaluation_mode="offline",
            run_metadata={"search_implementation_version": "fixed-fixture"},
        )
        self.assertEqual(offline_summary["evaluation_mode"], "offline")
        self.assertEqual(offline_summary["dataset_type"], "synthetic_test")

        with self.assertRaisesRegex(GoldenSetValidationError, "confirmed published"):
            await evaluate_golden_set(port, dataset, evaluation_mode="live")

        published_payload = _valid_chunk_dataset()
        published_payload["rag_publication_status"] = "confirmed_published"  # type: ignore[index]
        published_dataset = parse_golden_set(published_payload)
        live_port = FixedSearchPort({})
        complete_metadata = {
            "search_implementation_version": "commit-sha",
            "search_snapshot_version": "snapshot-v1",
            "embedding_model_id": "embedding-model",
            "embedding_model_revision": "revision-1",
        }
        with self.assertRaisesRegex(GoldenSetValidationError, "reproducibility metadata"):
            await evaluate_golden_set(
                live_port,
                published_dataset,
                evaluation_mode="live",
            )
        self.assertEqual(live_port.requests, [])

        live_port = FixedSearchPort({})
        live_summary = await evaluate_golden_set(
            live_port,
            published_dataset,
            evaluation_mode="live",
            run_metadata=complete_metadata,
        )
        self.assertEqual(live_summary["evaluation_mode"], "live")
        self.assertEqual(live_summary["dataset_type"], "synthetic_test")
        self.assertEqual(live_summary["collection_id"], "rag-test-unit")
        self.assertEqual(len(live_port.requests), 2)
        self.assertTrue(all(request.top_k == 10 for request in live_port.requests))


class GoldenSetChunkMetricTests(unittest.IsolatedAsyncioTestCase):
    async def test_같은_위치의_청크를_id로_구분하고_중복_검색을_제거한다(self) -> None:
        payload = _valid_chunk_dataset()
        payload["queries"] = [payload["queries"][0]]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        first_id, second_id = [label.evidence_id for label in dataset.queries[0].relevant_evidence]
        port = FixedSearchPort(
            {
                dataset.queries[0].question: (
                    _retrieved_evidence(first_id, location=SYNTHETIC_LOCATION_1),
                    _retrieved_evidence(first_id, location=SYNTHETIC_LOCATION_1),
                    _retrieved_evidence("noise", location=SYNTHETIC_LOCATION_1),
                    _retrieved_evidence(second_id, location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["label_level"], "chunk")
        self.assertEqual(summary["metrics"]["recall_at_3"], 0.5)
        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 1.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 1.0)
        self.assertEqual(port.requests, [SearchRequest(dataset.queries[0].question, top_k=10)])
        query_result = summary["per_query_results"][0]
        self.assertEqual(query_result["metrics"]["recall_at_10"], 1.0)
        self.assertEqual(query_result["ranked_evidence"][3]["rank"], 4)
        self.assertEqual(query_result["ranked_evidence"][3]["evidence_id"], second_id)

    async def test_출처가_다른_동일_청크_id를_정답으로_인정하지_않는다(self) -> None:
        payload = _valid_chunk_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        label = dataset.queries[0].relevant_evidence[0]
        assert label.evidence_id is not None
        port = FixedSearchPort(
            {
                dataset.queries[0].question: (
                    _retrieved_evidence(label.evidence_id, source_id="wrong-source"),
                    _retrieved_evidence(label.evidence_id, version="2025-01-01"),
                    _retrieved_evidence(
                        label.evidence_id,
                        official_url="https://official.example.gov/other-page",
                    ),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_10"], 0.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 0.0)
        self.assertTrue(
            all(
                not hit["is_relevant"] for hit in summary["per_query_results"][0]["ranked_evidence"]
            )
        )

    async def test_청크_부분_매핑을_제외하고_전체_미매핑_지표를_null로_반환한다(
        self,
    ) -> None:
        payload = _valid_chunk_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"][1]["evidence_id"] = None  # type: ignore[index]
        query["relevant_evidence"][1]["location_mapping_status"] = "unmapped"  # type: ignore[index]
        query["relevant_evidence"][1]["location_match_key"] = None  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort({})

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["partially_mapped_query_count"], 1)
        self.assertEqual(summary["evaluated_query_count"], 0)
        self.assertEqual(summary["evaluation_excluded_query_count"], 1)
        self.assertEqual(summary["metrics"]["recall_at_3"], None)
        self.assertEqual(summary["metrics"]["recall_at_10"], None)
        self.assertEqual(summary["metrics"]["mrr_at_3"], None)
        self.assertEqual(summary["metrics"]["mrr_at_10"], None)
        self.assertEqual(port.requests, [])


class CurrentGoldenSetDataTests(unittest.TestCase):
    def test_현재_합성_랭킹_데이터셋의_매핑된_청크_id를_확인한다(self) -> None:
        dataset_path = (
            Path(__file__).resolve().parents[1]
            / "rag/evaluation/golden_set_synthetic_ranking_v1.json"
        )

        dataset = load_golden_set(dataset_path)

        self.assertEqual(dataset.dataset_type, "synthetic_test")
        self.assertEqual(dataset.dataset_version, "synthetic-ranking-05b16cbf43c4-v1")
        self.assertEqual(dataset.label_level, "chunk")
        self.assertEqual(dataset.collection_id, "rag-test-05b16cbf43c4-ranking")
        self.assertEqual(dataset.rag_publication_status, "confirmed_published")
        self.assertRegex(dataset.search_snapshot_version or "", r"^[0-9a-f]{64}$")
        self.assertEqual(len(dataset.queries), 2)
        labels = [label for query in dataset.queries for label in query.relevant_evidence]
        self.assertEqual(len(labels), 2)
        self.assertTrue(all(label.evidence_id is not None for label in labels))
        self.assertTrue(all(label.source_id is not None for label in labels))
        self.assertTrue(all(label.location_mapping_status == "mapped" for label in labels))
        self.assertTrue(all(label.supporting_text is not None for label in labels))
        self.assertTrue(all(label.location_match_key is not None for label in labels))


class GoldenSetBoundaryMetricTests(unittest.IsolatedAsyncioTestCase):
    async def test_정답_라벨_하나의_recall을_계산한다(self) -> None:
        payload = _valid_dataset()
        query = payload["queries"][0]  # type: ignore[index]
        query["relevant_evidence"] = query["relevant_evidence"][:1]  # type: ignore[index]
        payload["queries"] = [query]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("location-hit", location=SYNTHETIC_LOCATION_1),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 1.0)
        self.assertEqual(summary["metrics"]["recall_at_10"], 1.0)

    async def test_4위_정답의_recall과_mrr이_3위와_10위에서_달라진다(self) -> None:
        payload = _valid_dataset()
        payload["queries"] = [payload["queries"][0]]  # type: ignore[index]
        dataset = parse_golden_set(payload)
        port = FixedSearchPort(
            {
                "첫 번째 위치의 내용을 알려줘.": (
                    _retrieved_evidence("noise-1", location=SYNTHETIC_LOCATION_7),
                    _retrieved_evidence("noise-2", location=SYNTHETIC_LOCATION_8),
                    _retrieved_evidence("noise-3", location=SYNTHETIC_LOCATION_9),
                    _retrieved_evidence("answer", location=SYNTHETIC_LOCATION_2),
                )
            }
        )

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["metrics"]["recall_at_3"], 0.0)
        self.assertEqual(summary["metrics"]["recall_at_10"], 0.5)
        self.assertEqual(summary["metrics"]["mrr_at_3"], 0.0)
        self.assertEqual(summary["metrics"]["mrr_at_10"], 0.25)

    async def test_질문이_없는_데이터셋의_지표와_반환율을_null로_계산한다(self) -> None:
        payload = _valid_dataset()
        payload["queries"] = []  # type: ignore[index]
        dataset = parse_golden_set(payload)

        summary = await evaluate_golden_set(FixedSearchPort({}), dataset, evaluation_mode="offline")

        self.assertEqual(summary["query_count"], 0)
        self.assertEqual(
            summary["metrics"],
            {
                "recall_at_3": None,
                "recall_at_10": None,
                "mrr_at_3": None,
                "mrr_at_10": None,
            },
        )
        self.assertIsNone(summary["result_return_rate"])

    async def test_미검증_질문은_검색에서_제외하고_사유를_기록한다(self) -> None:
        payload = _valid_dataset()
        payload["queries"].append(  # type: ignore[union-attr]
            {
                "query_id": "q-unverified",
                "question": "출처 버전이 확인되지 않은 질문",
                "question_type": "direct",
                "verification_status": "unverified",
                "relevant_evidence": [],
                "exclusion_reason": "공식 문서 버전 확인 대기",
            }
        )
        dataset = parse_golden_set(payload)
        port = FixedSearchPort({})

        summary = await evaluate_golden_set(port, dataset, evaluation_mode="offline")

        self.assertEqual(summary["excluded_query_count"], 1)
        self.assertEqual(
            summary["excluded_queries"],
            [{"query_id": "q-unverified", "reason": "공식 문서 버전 확인 대기"}],
        )
        self.assertNotIn("출처 버전이 확인되지 않은 질문", [r.query for r in port.requests])
