# 담당: [D] | 책임: 검색 Golden Set의 검증과 검색 품질 지표.
# PRD: E6 / 스토리 6-4 / 태스크 6-4-1
# 구현할 기능: 검증된 정답 라벨로 Recall@K와 MRR@K를 산출한다.
# 완료 기준: 검색 Port 주입만으로 오프라인 평가와 재현 요약을 제공한다.
# 제한사항: 청크 라벨과 문서·위치 라벨을 섞지 않고 법률 안전성 승인으로 간주하지 않는다.

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from starter_rag.contracts.models import Evidence, SearchRequest
from starter_rag.contracts.ports import SearchPort

LabelLevel = Literal["chunk", "document_location"]
DatasetType = Literal["official_verified", "synthetic_test"]
QuestionType = Literal[
    "direct",
    "paraphrase",
    "multi_source",
    "location_sensitive",
    "contrastive",
    "no_answer",
]
VerificationStatus = Literal["verified", "verified_no_answer", "unverified"]
LocationMappingStatus = Literal["mapped", "unmapped"]
EvaluationMode = Literal["offline", "live"]

QUESTION_TYPES = frozenset(
    {"direct", "paraphrase", "multi_source", "location_sensitive", "contrastive", "no_answer"}
)
RUN_METADATA_FIELDS = frozenset(
    {
        "search_implementation_version",
        "search_snapshot_version",
        "embedding_model_id",
        "embedding_model_revision",
    }
)


class GoldenSetValidationError(ValueError):
    """Golden Set 데이터나 평가 출처가 선언된 계약을 위반할 때 발생한다."""


@dataclass(frozen=True)
class RelevantEvidence:
    source_id: str | None
    source_title: str
    publisher: str
    version: str
    evidence_id: str | None
    location: str
    location_mapping_status: LocationMappingStatus | None
    location_match_key: str | None
    official_url: str
    supporting_text: str | None


@dataclass(frozen=True)
class GoldenQuery:
    query_id: str
    question: str
    question_type: QuestionType
    verification_status: VerificationStatus
    relevant_evidence: tuple[RelevantEvidence, ...]
    exclusion_reason: str | None
    verification_note: str | None


@dataclass(frozen=True)
class GoldenSet:
    dataset_version: str
    dataset_type: DatasetType
    label_level: LabelLevel
    scope: str
    collection_id: str | None
    rag_publication_status: Literal["confirmed_published", "unconfirmed"]
    search_snapshot_version: str | None
    queries: tuple[GoldenQuery, ...]


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoldenSetValidationError(f"{path}: expected an object")
    return value


def _required_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoldenSetValidationError(f"{path}: expected a non-empty string")
    return value.strip()


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, path)


def _required_confirmed_string(value: object, path: str) -> str:
    result = _required_string(value, path)
    unknown_markers = {"unknown", "n/a", "tbd", "미확인", "미정", "확인 필요", "알 수 없음"}
    if result.casefold() in unknown_markers:
        raise GoldenSetValidationError(
            f"{path}: unconfirmed values cannot be used as verified labels"
        )
    return result


def _https_url(value: object, path: str) -> str:
    url = _required_string(value, path)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise GoldenSetValidationError(f"{path}: official_url must be an absolute HTTPS URL")
    return url


def _check_keys(
    data: Mapping[str, object], *, required: set[str], allowed: set[str], path: str
) -> None:
    missing = required - data.keys()
    if missing:
        raise GoldenSetValidationError(
            f"{path}: missing required field(s): {', '.join(sorted(missing))}"
        )
    unexpected = data.keys() - allowed
    if unexpected:
        raise GoldenSetValidationError(
            f"{path}: unexpected field(s): {', '.join(sorted(unexpected))}"
        )


def _canonical_location_key(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        decoded = json.loads(
            value,
            parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(constant)),
        )
    except (json.JSONDecodeError, ValueError):
        return None
    if (
        not isinstance(decoded, list)
        or not decoded
        or any(
            not isinstance(item, Mapping)
            or not item
            or any(not isinstance(key, str) or not key for key in item)
            for item in decoded
        )
    ):
        return None
    return json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_chunk_location_key(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        decoded = json.loads(
            value,
            parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(constant)),
        )
        if not isinstance(decoded, (Mapping, list)) or not decoded:
            return None
        return json.dumps(
            decoded,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _parse_relevant_evidence(
    value: object, *, path: str, label_level: LabelLevel
) -> RelevantEvidence:
    data = _mapping(value, path)
    fields = {
        "source_id",
        "source_title",
        "publisher",
        "version",
        "evidence_id",
        "location",
        "official_url",
    }
    if label_level == "document_location":
        mapping_fields = {"location_mapping_status", "location_match_key"}
        required_fields = fields | mapping_fields
        allowed_fields = required_fields
    else:
        mapping_fields = {"location_mapping_status", "supporting_text"}
        required_fields = fields | mapping_fields
        allowed_fields = required_fields | {"location_match_key"}
    _check_keys(data, required=required_fields, allowed=allowed_fields, path=path)

    source_id = _optional_string(data["source_id"], f"{path}.source_id")
    evidence_id = _optional_string(data["evidence_id"], f"{path}.evidence_id")
    if label_level == "document_location" and evidence_id is not None:
        raise GoldenSetValidationError(
            f"{path}.evidence_id: document_location labels cannot contain chunk IDs"
        )

    mapping_status: LocationMappingStatus | None = None
    location_match_key: str | None = None
    supporting_text: str | None = None
    if label_level == "document_location":
        raw_status = _required_string(
            data["location_mapping_status"], f"{path}.location_mapping_status"
        )
        if raw_status not in {"mapped", "unmapped"}:
            raise GoldenSetValidationError(
                f"{path}.location_mapping_status: expected 'mapped' or 'unmapped'"
            )
        mapping_status = raw_status  # type: ignore[assignment]
        raw_match_key = data["location_match_key"]
        if mapping_status == "mapped":
            if source_id is None:
                raise GoldenSetValidationError(
                    f"{path}.source_id: mapped locations require a verified source ID"
                )
            location_match_key = _canonical_location_key(raw_match_key)
            if location_match_key is None:
                raise GoldenSetValidationError(
                    f"{path}.location_match_key: mapped locations require a non-empty structured JSON list"
                )
        elif raw_match_key is not None:
            raise GoldenSetValidationError(
                f"{path}.location_match_key: must be null for unmapped locations"
            )
    else:
        raw_status = _required_string(
            data["location_mapping_status"], f"{path}.location_mapping_status"
        )
        if raw_status not in {"mapped", "unmapped"}:
            raise GoldenSetValidationError(
                f"{path}.location_mapping_status: expected 'mapped' or 'unmapped'"
            )
        mapping_status = raw_status  # type: ignore[assignment]
        supporting_text = _optional_string(data["supporting_text"], f"{path}.supporting_text")
        raw_match_key = data.get("location_match_key")
        if raw_match_key is not None:
            location_match_key = _canonical_chunk_location_key(raw_match_key)
            if location_match_key is None:
                raise GoldenSetValidationError(
                    f"{path}.location_match_key: expected a structured JSON object or array"
                )
        if mapping_status == "mapped":
            if evidence_id is None or source_id is None:
                raise GoldenSetValidationError(
                    f"{path}: mapped chunk labels require evidence_id and source_id"
                )
            if supporting_text is None:
                raise GoldenSetValidationError(
                    f"{path}.supporting_text: mapped chunk labels require a source text anchor"
                )
        elif evidence_id is not None:
            raise GoldenSetValidationError(
                f"{path}.evidence_id: must be null for unmapped chunk labels"
            )
        elif raw_match_key is not None:
            raise GoldenSetValidationError(
                f"{path}.location_match_key: must be null for unmapped chunk labels"
            )

    return RelevantEvidence(
        source_id=source_id,
        source_title=_required_confirmed_string(data["source_title"], f"{path}.source_title"),
        publisher=_required_confirmed_string(data["publisher"], f"{path}.publisher"),
        version=_required_confirmed_string(data["version"], f"{path}.version"),
        evidence_id=evidence_id,
        location=_required_confirmed_string(data["location"], f"{path}.location"),
        location_mapping_status=mapping_status,
        location_match_key=location_match_key,
        official_url=_https_url(data["official_url"], f"{path}.official_url"),
        supporting_text=supporting_text,
    )


def _label_key(label: RelevantEvidence, label_level: LabelLevel) -> tuple[object, ...]:
    if label_level == "chunk":
        if label.evidence_id is not None:
            return (label.evidence_id,)
        return (
            "unmapped",
            _url_identity(label.official_url),
            label.version,
            _normalize_location(label.location),
            label.supporting_text,
        )
    return (
        _url_identity(label.official_url),
        label.version,
        _normalize_location(label.location),
    )


def _url_identity(url: str) -> tuple[object, ...]:
    parsed = urlsplit(url)
    hostname = parsed.hostname.casefold() if parsed.hostname is not None else None
    if (
        parsed.scheme.casefold() == "https"
        and hostname in {"fsc.go.kr", "www.fsc.go.kr"}
        and parsed.path in {"/po010101/87657", "/po010104/87657"}
        and parsed.port in {None, 443}
    ):
        significant_query = tuple(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() != "curpage" and not key.casefold().startswith("srch")
        )
        return (
            "fsc_article",
            parsed.scheme.casefold(),
            "fsc.go.kr",
            "/po010101/87657",
            significant_query,
            parsed.fragment,
        )
    return ("exact", url)


def _normalize_location(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def parse_golden_set(payload: Mapping[str, object]) -> GoldenSet:
    """메모리의 Golden Set 데이터를 파싱하고 선언된 형식과 매핑 상태를 검증한다."""
    data = _mapping(payload, "dataset")
    root_fields = {
        "dataset_version",
        "dataset_type",
        "label_level",
        "scope",
        "rag_publication_status",
        "search_snapshot_version",
        "queries",
    }
    _check_keys(data, required=root_fields, allowed=root_fields | {"collection_id"}, path="dataset")

    dataset_type = _required_string(data["dataset_type"], "dataset.dataset_type")
    if dataset_type not in {"official_verified", "synthetic_test"}:
        raise GoldenSetValidationError(
            "dataset.dataset_type: expected 'official_verified' or 'synthetic_test'"
        )
    label_level = _required_string(data["label_level"], "dataset.label_level")
    if label_level not in {"chunk", "document_location"}:
        raise GoldenSetValidationError(
            "dataset.label_level: expected 'chunk' or 'document_location'"
        )
    collection_id = _optional_string(data.get("collection_id"), "dataset.collection_id")
    if label_level == "chunk" and collection_id is None:
        raise GoldenSetValidationError("dataset.collection_id: required for chunk-level labels")

    rag_publication_status = _required_string(
        data["rag_publication_status"], "dataset.rag_publication_status"
    )
    if rag_publication_status not in {"confirmed_published", "unconfirmed"}:
        raise GoldenSetValidationError(
            "dataset.rag_publication_status: expected 'confirmed_published' or 'unconfirmed'"
        )

    raw_queries = data["queries"]
    if not isinstance(raw_queries, Sequence) or isinstance(raw_queries, (str, bytes)):
        raise GoldenSetValidationError("dataset.queries: expected an array")

    queries: list[GoldenQuery] = []
    seen_query_ids: set[str] = set()
    query_required_fields = {
        "query_id",
        "question",
        "question_type",
        "verification_status",
        "relevant_evidence",
    }
    query_allowed_fields = query_required_fields | {"exclusion_reason", "verification_note"}
    for index, raw_query in enumerate(raw_queries):
        path = f"dataset.queries[{index}]"
        query_data = _mapping(raw_query, path)
        _check_keys(
            query_data, required=query_required_fields, allowed=query_allowed_fields, path=path
        )
        query_id = _required_string(query_data["query_id"], f"{path}.query_id")
        query_path = f"query {query_id}"
        if query_id in seen_query_ids:
            raise GoldenSetValidationError(f"{query_path}: duplicate query_id")
        seen_query_ids.add(query_id)

        question = _required_string(query_data["question"], f"{query_path}.question")
        question_type = _required_string(query_data["question_type"], f"{query_path}.question_type")
        if question_type not in QUESTION_TYPES:
            raise GoldenSetValidationError(
                f"{query_path}.question_type: invalid type {question_type!r}"
            )
        verification_status = _required_string(
            query_data["verification_status"], f"{query_path}.verification_status"
        )
        if verification_status not in {"verified", "verified_no_answer", "unverified"}:
            raise GoldenSetValidationError(
                f"{query_path}.verification_status: invalid status {verification_status!r}"
            )

        raw_labels = query_data["relevant_evidence"]
        if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, (str, bytes)):
            raise GoldenSetValidationError(f"{query_path}.relevant_evidence: expected an array")
        labels = tuple(
            _parse_relevant_evidence(
                label,
                path=f"{query_path}.relevant_evidence[{label_index}]",
                label_level=label_level,
            )
            for label_index, label in enumerate(raw_labels)
        )
        label_keys = [_label_key(label, label_level) for label in labels]
        if len(label_keys) != len(set(label_keys)):
            raise GoldenSetValidationError(f"{query_path}: duplicate relevant evidence label")

        exclusion_reason = _optional_string(
            query_data.get("exclusion_reason"), f"{query_path}.exclusion_reason"
        )
        verification_note = _optional_string(
            query_data.get("verification_note"), f"{query_path}.verification_note"
        )
        if verification_status == "verified":
            if question_type == "no_answer" or not labels:
                raise GoldenSetValidationError(
                    f"{query_path}: verified answerable queries require relevant evidence"
                )
        elif verification_status == "verified_no_answer":
            if question_type != "no_answer" or labels or verification_note is None:
                raise GoldenSetValidationError(
                    f"{query_path}: verified no-answer queries require no labels and a verification_note"
                )
        else:
            if labels or exclusion_reason is None:
                raise GoldenSetValidationError(
                    f"{query_path}: unverified queries cannot carry answer labels and need an exclusion_reason"
                )

        queries.append(
            GoldenQuery(
                query_id=query_id,
                question=question,
                question_type=question_type,  # type: ignore[arg-type]
                verification_status=verification_status,  # type: ignore[arg-type]
                relevant_evidence=labels,
                exclusion_reason=exclusion_reason,
                verification_note=verification_note,
            )
        )

    return GoldenSet(
        dataset_version=_required_string(data["dataset_version"], "dataset.dataset_version"),
        dataset_type=dataset_type,  # type: ignore[arg-type]
        label_level=label_level,  # type: ignore[arg-type]
        scope=_required_string(data["scope"], "dataset.scope"),
        collection_id=collection_id,
        rag_publication_status=rag_publication_status,  # type: ignore[arg-type]
        search_snapshot_version=_optional_string(
            data["search_snapshot_version"], "dataset.search_snapshot_version"
        ),
        queries=tuple(queries),
    )


def load_golden_set(path: str | Path) -> GoldenSet:
    """JSON Golden Set 파일을 읽고 파싱 오류에 파일 경로를 포함한다."""
    dataset_path = Path(path)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldenSetValidationError(f"{dataset_path}: could not read valid JSON: {exc}") from exc
    return parse_golden_set(_mapping(payload, str(dataset_path)))


def _same_url(left: str, right: str) -> bool:
    return _url_identity(left) == _url_identity(right)


def validate_chunk_mapping(
    label: RelevantEvidence,
    record: Mapping[str, object],
    *,
    expected_collection_id: str = "published-guides",
    expected_is_synthetic: bool = False,
) -> None:
    """DB 행의 출처와 본문으로 정답 청크의 신원을 확인하고 부적합한 매핑을 거부한다."""
    if label.location_mapping_status != "mapped" or label.evidence_id is None:
        raise GoldenSetValidationError("chunk mapping must be marked mapped with an evidence ID")
    if label.source_id is None or label.supporting_text is None:
        raise GoldenSetValidationError("chunk mapping requires source ID and supporting text")

    expected = {
        "chunk_id": label.evidence_id,
        "source_id": label.source_id,
        "version": label.version,
        "source_title": label.source_title,
        "publisher": label.publisher,
    }
    for field, expected_value in expected.items():
        actual = record.get(field)
        if not isinstance(actual, str) or actual != expected_value:
            raise GoldenSetValidationError(
                f"chunk mapping {field} does not match the verified label"
            )

    source_url = record.get("source_url")
    if not isinstance(source_url, str) or not _same_url(source_url, label.official_url):
        raise GoldenSetValidationError("chunk mapping source_url does not match the official URL")
    if record.get("publication_state") != "published":
        raise GoldenSetValidationError("chunk mapping requires a published chunk")
    if record.get("collection_id") != expected_collection_id:
        raise GoldenSetValidationError("chunk mapping collection_id does not match the dataset")
    if record.get("is_synthetic") is not expected_is_synthetic:
        raise GoldenSetValidationError("chunk mapping synthetic flag does not match the dataset")

    if label.location_match_key is not None:
        actual_location_key = _canonical_chunk_location_key(record.get("location"))
        if actual_location_key != label.location_match_key:
            raise GoldenSetValidationError(
                "chunk location metadata does not match the verified key"
            )

    content = record.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GoldenSetValidationError("chunk mapping requires stored chunk content")
    normalized_content = _normalize_location(content)
    normalized_anchor = _normalize_location(label.supporting_text)
    if normalized_anchor not in normalized_content:
        raise GoldenSetValidationError("chunk content does not contain the verified answer text")


def validate_chunk_mappings(
    dataset: GoldenSet, records_by_chunk_id: Mapping[str, Mapping[str, object]]
) -> int:
    """읽기 전용 DB 행으로 모든 매핑을 검증하고 중복을 제외한 정답 청크 수를 반환한다."""
    if dataset.label_level != "chunk":
        raise GoldenSetValidationError("chunk mapping validation requires a chunk-level dataset")
    if dataset.collection_id is None:
        raise GoldenSetValidationError("chunk mapping validation requires a declared collection_id")

    mapped_ids: set[str] = set()
    expected_is_synthetic = dataset.dataset_type == "synthetic_test"
    for query in dataset.queries:
        for label in query.relevant_evidence:
            if label.location_mapping_status == "unmapped":
                if label.evidence_id is not None:
                    raise GoldenSetValidationError(
                        "unmapped chunk labels cannot carry an evidence ID"
                    )
                continue
            if label.evidence_id is None:
                raise GoldenSetValidationError("mapped chunk labels require an evidence ID")
            record = records_by_chunk_id.get(label.evidence_id)
            if record is None:
                raise GoldenSetValidationError(
                    f"mapped evidence ID does not exist in the verified chunk inventory: {label.evidence_id}"
                )
            validate_chunk_mapping(
                label,
                record,
                expected_collection_id=dataset.collection_id,
                expected_is_synthetic=expected_is_synthetic,
            )
            mapped_ids.add(label.evidence_id)
    return len(mapped_ids)


def _matches_label(evidence: Evidence, label: RelevantEvidence, label_level: LabelLevel) -> bool:
    if label_level == "chunk":
        return (
            label.location_mapping_status == "mapped"
            and label.evidence_id is not None
            and label.source_id is not None
            and evidence.evidence_id == label.evidence_id
            and evidence.source.source_id == label.source_id
            and evidence.source.version == label.version
            and evidence.source.title == label.source_title
            and evidence.source.publisher == label.publisher
            and _same_url(evidence.source.url or "", label.official_url)
            and (
                label.location_match_key is None
                or _canonical_chunk_location_key(evidence.location) == label.location_match_key
            )
        )
    if label.location_mapping_status != "mapped" or label.location_match_key is None:
        return False

    # 공식 URL, 문서 버전, 구조화된 전체 위치가 모두 같아야 정답으로 인정한다.
    if label.source_id is not None and evidence.source.source_id != label.source_id:
        return False
    location_match_key = _canonical_location_key(evidence.location)
    return (
        _same_url(evidence.source.url or "", label.official_url)
        and evidence.source.version == label.version
        and location_match_key == label.location_match_key
    )


def _matched_label_indexes(
    evidence: Sequence[Evidence], labels: tuple[RelevantEvidence, ...], label_level: LabelLevel
) -> set[int]:
    return {
        label_index
        for label_index, label in enumerate(labels)
        if any(_matches_label(item, label, label_level) for item in evidence)
    }


def _reciprocal_rank(
    evidence: Sequence[Evidence], labels: tuple[RelevantEvidence, ...], label_level: LabelLevel
) -> float:
    for rank, item in enumerate(evidence, start=1):
        if any(_matches_label(item, label, label_level) for label in labels):
            return 1 / rank
    return 0.0


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


async def evaluate_golden_set(
    search_port: SearchPort,
    dataset: GoldenSet,
    *,
    evaluation_mode: EvaluationMode,
    run_metadata: Mapping[str, str | None] | None = None,
) -> dict[str, object]:
    """완전 매핑 질문마다 top_k=10 검색 한 번을 실행해 Recall과 MRR을 계산한다."""
    metadata = dict(run_metadata or {})
    unexpected_metadata = metadata.keys() - RUN_METADATA_FIELDS
    if unexpected_metadata:
        raise GoldenSetValidationError(
            f"run_metadata: unexpected field(s): {', '.join(sorted(unexpected_metadata))}"
        )
    invalid_metadata = {
        field
        for field, value in metadata.items()
        if value is not None and (not isinstance(value, str) or not value.strip())
    }
    if invalid_metadata:
        raise GoldenSetValidationError(
            "run_metadata values must be non-empty strings or null: "
            + ", ".join(sorted(invalid_metadata))
        )
    if evaluation_mode not in {"offline", "live"}:
        raise GoldenSetValidationError("evaluation_mode: expected 'offline' or 'live'")
    if evaluation_mode == "live":
        if dataset.rag_publication_status != "confirmed_published":
            raise GoldenSetValidationError(
                "live evaluation requires a confirmed published collection"
            )
        if dataset.label_level != "chunk":
            raise GoldenSetValidationError("live evaluation requires chunk-level labels")
        if dataset.collection_id is None:
            raise GoldenSetValidationError("live evaluation requires a declared collection_id")
        missing_metadata = {field for field in RUN_METADATA_FIELDS if not metadata.get(field)}
        if missing_metadata:
            raise GoldenSetValidationError(
                "live evaluation requires reproducibility metadata: "
                + ", ".join(sorted(missing_metadata))
            )

    answerable = [query for query in dataset.queries if query.verification_status == "verified"]
    no_answer = [
        query for query in dataset.queries if query.verification_status == "verified_no_answer"
    ]
    excluded = [query for query in dataset.queries if query.verification_status == "unverified"]
    all_labels = [label for query in answerable for label in query.relevant_evidence]
    mapped_labels = [label for label in all_labels if label.location_mapping_status == "mapped"]
    unmapped_labels = [label for label in all_labels if label.location_mapping_status == "unmapped"]

    mapped_by_query = {
        query.query_id: tuple(
            label for label in query.relevant_evidence if label.location_mapping_status == "mapped"
        )
        for query in answerable
    }
    fully_mapped_queries = [
        query
        for query in answerable
        if len(mapped_by_query[query.query_id]) == len(query.relevant_evidence)
    ]
    partially_mapped_queries = [
        query
        for query in answerable
        if mapped_by_query[query.query_id]
        and len(mapped_by_query[query.query_id]) < len(query.relevant_evidence)
    ]
    unmapped_queries = [
        query
        for query in answerable
        if not mapped_by_query[query.query_id]
        and any(label.location_mapping_status == "unmapped" for label in query.relevant_evidence)
    ]
    scoreable_queries = fully_mapped_queries
    is_blocked = bool(answerable) and not scoreable_queries
    evaluation_status = (
        "blocked_unmapped_labels"
        if is_blocked
        else "partial_unmapped"
        if unmapped_labels
        else "partial_unverified"
        if excluded
        else "complete"
    )

    # 완전 매핑 질문이 없으면 검색을 생략해 불완전한 라벨을 0점으로 오인하지 않게 한다.
    active_queries = [] if is_blocked else [*scoreable_queries, *no_answer]
    retrieved_by_query: dict[str, tuple[Evidence, ...]] = {}
    for query in active_queries:
        result = await search_port.search(SearchRequest(query=query.question, top_k=10))
        retrieved_by_query[query.query_id] = tuple(result.evidence[:10])

    recalls: dict[int, list[float]] = {3: [], 10: []}
    reciprocal_ranks: dict[int, list[float]] = {3: [], 10: []}
    per_query_metrics: dict[str, dict[str, float]] = {}
    for query in scoreable_queries:
        retrieved = retrieved_by_query[query.query_id]
        labels = mapped_by_query[query.query_id]
        query_metrics: dict[str, float] = {}
        for k in (3, 10):
            top_results = retrieved[:k]
            matched_labels = _matched_label_indexes(top_results, labels, dataset.label_level)
            recall = len(matched_labels) / len(labels)
            reciprocal_rank = _reciprocal_rank(top_results, labels, dataset.label_level)
            recalls[k].append(recall)
            reciprocal_ranks[k].append(reciprocal_rank)
            query_metrics[f"recall_at_{k}"] = round(recall, 4)
            query_metrics[f"mrr_at_{k}"] = round(reciprocal_rank, 4)
        per_query_metrics[query.query_id] = query_metrics

    per_query_results: list[dict[str, object]] = []
    for query in dataset.queries:
        query_labels = query.relevant_evidence
        retrieved = retrieved_by_query.get(query.query_id, ())
        if query.verification_status == "unverified":
            status = "unverified_excluded"
            exclusion_reason = query.exclusion_reason
        elif query.verification_status == "verified_no_answer":
            status = "no_answer_excluded"
            exclusion_reason = "no-answer questions are outside Recall/MRR denominators"
        elif query in partially_mapped_queries:
            status = "partial_mapping_excluded"
            exclusion_reason = "all relevant evidence must be mapped before scoring this query"
        elif query in unmapped_queries:
            status = "unmapped_excluded"
            exclusion_reason = "no relevant evidence label has a verified mapping"
        elif is_blocked:
            status = "not_searched"
            exclusion_reason = "no answerable query has a complete verified mapping"
        else:
            status = "evaluated"
            exclusion_reason = None

        ranked_evidence: list[dict[str, object]] = []
        for rank, item in enumerate(retrieved, start=1):
            matched_labels = [
                label for label in query_labels if _matches_label(item, label, dataset.label_level)
            ]
            ranked_evidence.append(
                {
                    "rank": rank,
                    "evidence_id": item.evidence_id,
                    "source_id": item.source.source_id,
                    "source_title": item.source.title,
                    "official_url": item.source.url,
                    "version": item.source.version,
                    "location": item.location,
                    "score": item.score,
                    "is_relevant": bool(matched_labels),
                    "matched_evidence_ids": [label.evidence_id for label in matched_labels],
                }
            )

        per_query_results.append(
            {
                "query_id": query.query_id,
                "question": query.question,
                "verification_status": query.verification_status,
                "evaluation_status": status,
                "exclusion_reason": exclusion_reason,
                "relevant_evidence": [
                    {
                        "evidence_id": label.evidence_id,
                        "location": label.location,
                        "mapping_status": label.location_mapping_status,
                    }
                    for label in query_labels
                ],
                "metrics": per_query_metrics.get(query.query_id),
                "ranked_evidence": ranked_evidence,
            }
        )

    returned_queries = sum(bool(retrieved_by_query[query.query_id]) for query in active_queries)
    no_answer_returned = sum(
        bool(retrieved_by_query.get(query.query_id, ())) for query in no_answer
    )
    return_rate = returned_queries / len(active_queries) if active_queries else None
    no_answer_return_rate = (
        no_answer_returned / len(no_answer) if no_answer and not is_blocked else None
    )
    source_id_mapped_labels = sum(label.source_id is not None for label in all_labels)
    location_mapping_coverage = (
        round(len(mapped_labels) / len(all_labels), 4)
        if dataset.label_level == "document_location" and all_labels
        else None
    )
    evaluation_excluded_queries = [
        {
            "query_id": result["query_id"],
            "reason": result["exclusion_reason"],
            "status": result["evaluation_status"],
        }
        for result in per_query_results
        if result["evaluation_status"] != "evaluated"
    ]
    verified_relevant_chunk_ids = {
        label.evidence_id
        for label in mapped_labels
        if dataset.label_level == "chunk" and label.evidence_id is not None
    }

    return {
        "dataset_version": dataset.dataset_version,
        "dataset_type": dataset.dataset_type,
        "evaluation_mode": evaluation_mode,
        "evaluation_status": evaluation_status,
        "retrieval_executed": bool(active_queries),
        "label_level": dataset.label_level,
        "label_scope": dataset.scope,
        "collection_id": dataset.collection_id,
        "retrieval_policy": "one_top_k_10_request_per_complete_answer_query; @3_uses_first_3_from_same_response; incomplete_questions_excluded",
        "label_match_policy": (
            "evidence_id_source_id_official_url_version_exact_location_key_supplemental"
            if dataset.label_level == "chunk"
            else "source_id_and_exact_official_url_version_structured_location"
        ),
        "rag_publication_status": dataset.rag_publication_status,
        "chunk_level_evaluable": dataset.label_level == "chunk",
        "relevant_label_count": len(all_labels),
        "mapped_relevant_label_count": len(mapped_labels),
        "unmapped_label_count": len(unmapped_labels),
        "verified_relevant_chunk_count": len(verified_relevant_chunk_ids),
        "location_mapping_coverage": location_mapping_coverage,
        "fully_mapped_query_count": len(fully_mapped_queries),
        "partially_mapped_query_count": len(partially_mapped_queries),
        "unmapped_query_count": len(unmapped_queries),
        "unmapped_queries": [
            {
                "query_id": query.query_id,
                "locations": [
                    label.location
                    for label in query.relevant_evidence
                    if label.location_mapping_status == "unmapped"
                ],
                "reason": "no relevant evidence label has a confirmed mapping",
            }
            for query in unmapped_queries
        ],
        "partially_mapped_queries": [
            {
                "query_id": query.query_id,
                "mapped_locations": [
                    label.location
                    for label in query.relevant_evidence
                    if label.location_mapping_status == "mapped"
                ],
                "unmapped_locations": [
                    label.location
                    for label in query.relevant_evidence
                    if label.location_mapping_status == "unmapped"
                ],
                "reason": "the full relevant evidence set must be mapped before scoring",
            }
            for query in partially_mapped_queries
        ],
        "source_id_mapped_label_count": source_id_mapped_labels,
        "source_id_mapping_coverage": (
            round(source_id_mapped_labels / len(all_labels), 4) if all_labels else 0.0
        ),
        "search_target_snapshot_version": metadata.get("search_snapshot_version")
        or dataset.search_snapshot_version,
        "query_count": len(dataset.queries),
        "total_question_count": len(dataset.queries),
        "answerable_query_count": len(answerable),
        "evaluated_query_count": len(scoreable_queries),
        "evaluation_excluded_query_count": len(evaluation_excluded_queries),
        "no_answer_query_count": len(no_answer),
        "excluded_query_count": len(excluded),
        "excluded_queries": [
            {"query_id": query.query_id, "reason": query.exclusion_reason} for query in excluded
        ],
        "evaluation_excluded_queries": evaluation_excluded_queries,
        "per_query_results": per_query_results,
        "metrics": {
            "recall_at_3": _mean(recalls[3]),
            "recall_at_10": _mean(recalls[10]),
            "mrr_at_3": _mean(reciprocal_ranks[3]),
            "mrr_at_10": _mean(reciprocal_ranks[10]),
        },
        "returned_result_query_count": returned_queries,
        "result_return_rate": round(return_rate, 4) if return_rate is not None else None,
        "no_answer_returned_result_query_count": no_answer_returned,
        "no_answer_result_return_rate": (
            round(no_answer_return_rate, 4) if no_answer_return_rate is not None else None
        ),
        "run_metadata": {field: metadata.get(field) for field in sorted(RUN_METADATA_FIELDS)},
    }
