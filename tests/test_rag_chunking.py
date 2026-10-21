from __future__ import annotations

import asyncio
import builtins
import hashlib
import importlib
import io
import json
import logging
import sys
import traceback
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from unittest.mock import Mock, patch
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from starter_rag.ingestion import chunking_model, service
from starter_rag.ingestion.chunking import (
    ChunkIntegrityError,
    DocumentChunk,
    UnresolvedCellTextError,
    chunk_document,
    validate_chunk_integrity,
)
from starter_rag.ingestion.parser import (
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    SourceProvenance,
    TableCellStructure,
    TableRowStructure,
    TableStructure,
    UnverifiedItem,
)


class _RateLimitError(RuntimeError):
    status_code = 429


class _RateLimitCause(RuntimeError):
    code = 429


class _GoogleRateLimitError(RuntimeError):
    status = "RESOURCE_EXHAUSTED"

    def __init__(self, secret: str) -> None:
        encoded = quote(secret, safe="")
        mixed_case = encoded.replace("%2F", "%2f")
        super().__init__(
            "Gemini request failed: "
            f"https://example.test/?key={secret}&lower={encoded.lower()}&mixed={mixed_case}"
        )
        self.__cause__ = RuntimeError(f"wrapped provider error contains {secret} and {encoded}")


class _MockChatModel(BaseChatModel):
    # 실제 호출 없이 응답 횟수와 모델 실패를 제어하는 LangChain 모델.

    def __init__(self, responses: tuple[object, ...]) -> None:
        super().__init__()
        self._responses = list(responses)
        self._calls = 0
        self._message_history: list[list[BaseMessage]] = []

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def last_messages(self) -> list[BaseMessage]:
        return self._message_history[-1]

    @property
    def _llm_type(self) -> str:
        return "test-only"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self._calls += 1
        self._message_history.append(messages)
        if not self._responses:
            raise AssertionError("예상하지 않은 추가 LLM 호출입니다.")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(response)))])


def _configured_model_factory(*, ollama_factory: Any = None, gemini_factory: Any = None) -> Any:
    return lambda environ: chunking_model.create_chunking_model_from_environment(
        environ,
        ollama_factory=ollama_factory,
        gemini_factory=gemini_factory,
    )


def _location(
    status: Literal["verified", "not_applicable", "unverified"] = "unverified",
) -> DocumentLocation:
    provenance = SourceProvenance(
        page_no=3,
        bbox=None,
        charspan=(7, 19),
    )
    return DocumentLocation(
        status=status,
        page_numbers=(3,) if status == "verified" else (),
        provenance=(provenance,),
    )


def _element(
    text: str,
    *,
    kind: Literal["document_title", "section_title", "paragraph"] = "paragraph",
    self_ref: str | None = None,
    original_text: str | None = None,
    location: DocumentLocation | None = None,
) -> DocumentElement:
    return DocumentElement(
        kind=kind,
        text=text,
        original_text=original_text,
        self_ref=self_ref,
        level=1 if kind == "section_title" else None,
        location=location or _location(),
        table=None,
    )


def _cell(
    text: str,
    row: int,
    column: int,
    *,
    end_row: int | None = None,
    end_column: int | None = None,
    row_span: int | None = None,
    column_span: int | None = None,
    column_header: bool = False,
    row_header: bool = False,
    self_ref: str | None = None,
) -> TableCellStructure:
    last_row = end_row if end_row is not None else row + 1
    last_column = end_column if end_column is not None else column + 1
    return TableCellStructure(
        text=text,
        start_row=row,
        end_row=last_row,
        start_column=column,
        end_column=last_column,
        row_span=row_span if row_span is not None else last_row - row,
        column_span=column_span if column_span is not None else last_column - column,
        column_header=column_header,
        row_header=row_header,
        row_section=False,
        fillable=False,
        self_ref=self_ref,
        bbox=None,
    )


def _table_element(
    row_count: int,
    column_count: int,
    cells: tuple[TableCellStructure, ...],
    *,
    self_ref: str | None = "#/tables/1",
    location: DocumentLocation | None = None,
) -> DocumentElement:
    rows = tuple(
        TableRowStructure(
            row_index=row_index,
            cell_indexes=tuple(
                cell_index for cell_index, cell in enumerate(cells) if cell.start_row == row_index
            ),
        )
        for row_index in range(row_count)
    )
    return DocumentElement(
        kind="table",
        text=None,
        original_text=None,
        self_ref=self_ref,
        level=None,
        location=location or _location(),
        table=TableStructure(
            row_count=row_count,
            column_count=column_count,
            rows=rows,
            cells=cells,
        ),
    )


def _structure(
    *elements: DocumentElement,
    unverified_items: tuple[UnverifiedItem, ...] = (),
) -> DocumentStructure:
    return DocumentStructure(
        source_format="xlsx",
        elements=tuple(elements),
        unverified_items=unverified_items,
    )


def _tokens(text: str) -> int:
    # 테스트 전용 단어 토큰 계산기. 운영 토크나이저를 흉내 내지 않는다.
    return len(text.split())


def _response(*groups: tuple[str, ...]) -> str:
    return json.dumps({"groups": groups}, ensure_ascii=False)


def _chunk(
    structure: DocumentStructure,
    model: _MockChatModel | None = None,
    *,
    count_tokens=_tokens,
    target_tokens: int = 512,
):
    return asyncio.run(
        chunk_document(
            structure,
            source_id="guide-1",
            version="v1",
            model=model or _MockChatModel(()),
            count_tokens=count_tokens,
            target_tokens=target_tokens,
        )
    )


def _validate_chunks(structure: DocumentStructure, chunks: tuple[DocumentChunk, ...]) -> None:
    validate_chunk_integrity(
        structure,
        chunks,
        source_id="guide-1",
        version="v1",
        count_tokens=_tokens,
    )


class AgenticDocumentChunkingTests(unittest.TestCase):
    def test_인접_요소_ID_그룹과_원문_공백을_보존한다(self) -> None:
        structure = _structure(
            _element("문서 제목 ", kind="document_title"),
            _element(" 절 제목\n", kind="section_title", original_text=" 절 제목 "),
            _element("  본문\n그대로  ", self_ref=None),
        )
        model = _MockChatModel((_response(("e000001", "e000002"), ("e000003",)),))

        chunks = _chunk(structure, model)

        self.assertEqual(
            [chunk.element_ids for chunk in chunks], [("e000001", "e000002"), ("e000003",)]
        )
        self.assertEqual(chunks[0].text, "문서 제목 \n 절 제목\n")
        self.assertEqual(chunks[1].text, "  본문\n그대로  ")
        self.assertEqual(chunks[0].generation_method, "agentic")
        self.assertEqual(chunks[0].source_elements[0].text, "문서 제목 ")
        self.assertEqual(chunks[0].source_elements[1].text, " 절 제목\n")
        self.assertEqual(chunks[0].source_elements[1].original_text, " 절 제목 ")
        self.assertEqual(chunks[1].locations, (structure.elements[2].location,))

    def test_표를_가로지르는_일반_요소_그룹을_만들지_않는다(self) -> None:
        table = _table_element(1, 1, (_cell("값", 0, 0),))
        structure = _structure(_element("앞 문단"), table, _element("뒤 문단"))
        model = _MockChatModel((_response(("e000001",), ("e000003",)),))

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 1)
        self.assertEqual([chunk.kind for chunk in chunks], ["document", "table_row", "document"])
        self.assertEqual(chunks[0].element_ids, ("e000001",))
        self.assertEqual(chunks[1].table_row.row_index, 0)
        self.assertEqual(chunks[2].element_ids, ("e000003",))

    def test_비인접_ID_그룹은_재요청하고_원문_순서를_유지한다(self) -> None:
        structure = _structure(_element("가"), _element("나"), _element("다"))
        model = _MockChatModel(
            (
                _response(("e000001", "e000003"), ("e000002",)),
                _response(("e000001",), ("e000002", "e000003")),
            )
        )

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 2)
        self.assertEqual(
            [chunk.element_ids for chunk in chunks], [("e000001",), ("e000002", "e000003")]
        )

    def test_목표_토큰을_넘는_다중_요소_그룹은_재요청한다(self) -> None:
        structure = _structure(_element("가"), _element("나"))
        model = _MockChatModel(
            (
                _response(("e000001", "e000002")),
                _response(("e000001",), ("e000002",)),
            )
        )
        token_counter = lambda text: 513 if text == "가\n나" else 1

        chunks = _chunk(structure, model, count_tokens=token_counter, target_tokens=512)

        self.assertEqual(model.calls, 2)
        self.assertEqual([chunk.element_ids for chunk in chunks], [("e000001",), ("e000002",)])

    def test_모델_실패_fallback도_목표_토큰에_맞춰_인접_그룹을_만든다(self) -> None:
        structure = _structure(_element("가"), _element("나"), _element("다"))
        model = _MockChatModel(("{}", "{}", "{}", "{}"))
        token_counts = {"가": 1, "나": 1, "다": 1, "가\n나": 2, "가\n나\n다": 3}
        token_counter = lambda text: token_counts.get(text, 1)

        chunks = _chunk(structure, model, count_tokens=token_counter, target_tokens=2)

        self.assertEqual(
            [chunk.element_ids for chunk in chunks], [("e000001", "e000002"), ("e000003",)]
        )
        self.assertEqual([chunk.token_count for chunk in chunks], [2, 1])

    def test_ID_누락_중복_순서변경을_거부하고_결정적_fallback을_기록한다(self) -> None:
        structure = _structure(_element("가"), _element("나"), _element("다"))
        invalid = (
            _response(("e000001",), ("e000003",)),
            _response(("e000001", "e000001"), ("e000002", "e000003")),
            _response(("e000002", "e000001"), ("e000003",)),
            _response(("e000001", "e000003"), ("e000002",)),
        )
        model = _MockChatModel(invalid)

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 4)
        self.assertTrue(all(chunk.generation_method == "deterministic" for chunk in chunks))
        self.assertTrue(all(chunk.fallback_used for chunk in chunks))
        self.assertTrue(all(chunk.model_status == "failed" for chunk in chunks))

    def test_잘못된_JSON은_재요청하고_성공_시도_횟수를_기록한다(self) -> None:
        structure = _structure(_element("본문"))
        model = _MockChatModel(("{깨진 JSON", _response(("e000001",))))

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 2)
        self.assertEqual(chunks[0].model_attempts, 2)
        self.assertEqual(chunks[0].model_status, "succeeded")

    def test_최대_세_번_재시도한_뒤_결정적_fallback을_기록한다(self) -> None:
        structure = _structure(_element("가"), _element("나"))
        model = _MockChatModel(("{}", "{}", "{}", "{}"))

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 4)
        self.assertTrue(all(chunk.fallback_used for chunk in chunks))
        self.assertTrue(all(chunk.model_failure for chunk in chunks))

    def test_HTTP_429는_재시도하지_않고_실패와_fallback을_기록한다(self) -> None:
        structure = _structure(_element("가"), _element("나"))
        model = _MockChatModel((_RateLimitError("429 rate limited"),))

        chunks = _chunk(structure, model)

        self.assertEqual(model.calls, 1)
        self.assertTrue(all(chunk.model_status == "failed" for chunk in chunks))
        self.assertTrue(all(chunk.fallback_used for chunk in chunks))
        self.assertTrue(all("429" in chunk.model_failure for chunk in chunks))

    def test_단일_512토큰_초과_요소는_자르지_않고_초과_표시한다(self) -> None:
        structure = _structure(_element("큰 본문"))
        model = _MockChatModel((_response(("e000001",)),))

        chunks = _chunk(
            structure,
            model,
            count_tokens=lambda text: 513 if text == "큰 본문" else 1,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "큰 본문")
        self.assertEqual(chunks[0].token_count, 513)
        self.assertTrue(chunks[0].over_target)
        system_prompt = model.last_messages[0].content
        self.assertIn("독립 그룹", system_prompt)
        self.assertIn("나누지 마세요", system_prompt)

    def test_기본_512토큰_목표와_요소별_토큰_수를_프롬프트에_넣는다(self) -> None:
        structure = _structure(_element("첫 요소"), _element("둘째 요소"))
        model = _MockChatModel((_response(("e000001",), ("e000002",)),))

        _chunk(structure, model)

        prompt = model.last_messages
        payload = json.loads(prompt[1].content)
        self.assertEqual(payload["target_tokens"], 512)
        self.assertEqual(
            [element["token_count"] for element in payload["segments"][0]["elements"]],
            [_tokens("첫 요소"), _tokens("둘째 요소")],
        )
        self.assertIn("512 토큰", prompt[0].content)

    def test_커스텀_목표와_외부_토큰_계산기_결과를_프롬프트에_넣는다(self) -> None:
        structure = _structure(_element("가"), _element("나"))
        model = _MockChatModel((_response(("e000001",), ("e000002",)),))
        token_counts = {"가": 2, "나": 4, "가\n나": 9}

        _chunk(
            structure,
            model,
            count_tokens=token_counts.__getitem__,
            target_tokens=7,
        )

        prompt = model.last_messages
        payload = json.loads(prompt[1].content)
        self.assertEqual(payload["target_tokens"], 7)
        self.assertEqual(
            [element["token_count"] for element in payload["segments"][0]["elements"]],
            [2, 4],
        )
        self.assertIn("최대 7 토큰", prompt[0].content)

    def test_에이전틱_성공_청크의_결정적_생성_표시는_거부한다(self) -> None:
        structure = _structure(_element("본문"))
        chunks = _chunk(structure, _MockChatModel((_response(("e000001",)),)))
        tampered = (replace(chunks[0], generation_method="deterministic"),)

        with self.assertRaises(ChunkIntegrityError):
            _validate_chunks(structure, tampered)

    def test_결정적_fallback_청크의_에이전틱_생성_표시는_거부한다(self) -> None:
        structure = _structure(_element("본문"))
        chunks = _chunk(structure, _MockChatModel(("{}", "{}", "{}", "{}")))
        tampered = (replace(chunks[0], generation_method="agentic"),)

        with self.assertRaises(ChunkIntegrityError):
            _validate_chunks(structure, tampered)

    def test_fallback_used가_불리언이_아니면_무결성_검증에서_거부한다(self) -> None:
        document_structure = _structure(_element("본문"))
        agentic_chunk = _chunk(
            document_structure,
            _MockChatModel((_response(("e000001",)),)),
        )[0]
        fallback_chunk = _chunk(document_structure, _MockChatModel(("{}",) * 4))[0]
        table_structure = _structure(_table_element(1, 1, (_cell("값", 0, 0),)))
        table_chunk = _chunk(table_structure)[0]

        invalid_values = (
            (document_structure, agentic_chunk, 0),
            (document_structure, fallback_chunk, 1),
            (table_structure, table_chunk, 0),
        )
        for structure, chunk, invalid_value in invalid_values:
            with self.subTest(kind=chunk.kind, value=invalid_value):
                tampered = (replace(chunk, fallback_used=invalid_value),)
                with self.assertRaises(ChunkIntegrityError):
                    _validate_chunks(structure, tampered)

    def test_빈_문서는_모델을_호출하지_않는다(self) -> None:
        model = _MockChatModel(())

        chunks = _chunk(_structure(), model)

        self.assertEqual(chunks, ())
        self.assertEqual(model.calls, 0)

    def test_self_ref가_없어도_내부_요소_ID가_충돌하지_않는다(self) -> None:
        structure = _structure(_element("같음", self_ref=None), _element("같음", self_ref=None))
        model = _MockChatModel((_response(("e000001",), ("e000002",)),))

        chunks = _chunk(structure, model)

        self.assertEqual(chunks[0].element_ids, ("e000001",))
        self.assertEqual(chunks[1].element_ids, ("e000002",))
        self.assertNotEqual(chunks[0].chunk_id, chunks[1].chunk_id)

    def test_같은_입력은_같은_Chunk_ID를_만든다(self) -> None:
        structure = _structure(_element("가"), _element("나"))
        response = _response(("e000001", "e000002"))

        first = _chunk(structure, _MockChatModel((response,)))
        second = _chunk(structure, _MockChatModel((response,)))

        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])
        self.assertTrue(all(chunk.chunk_id.startswith("sha256:") for chunk in first))

    def test_원문_변경을_무결성_검증에서_감지한다(self) -> None:
        structure = _structure(_element("원문"))
        chunks = _chunk(structure, _MockChatModel((_response(("e000001",)),)))
        tampered = (replace(chunks[0], text="변조"),)

        with self.assertRaises(ChunkIntegrityError):
            validate_chunk_integrity(
                structure,
                tampered,
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
            )


class XlsxRowChunkingTests(unittest.TestCase):
    def test_실제_행_범위보다_큰_row_span을_거부한다(self) -> None:
        table = _table_element(2, 1, (_cell("범위 오류", 0, 0, row_span=2),))

        with self.assertRaisesRegex(ChunkIntegrityError, "셀 0.*row_span"):
            _chunk(_structure(table))

    def test_실제_행_범위보다_작은_row_span을_거부한다(self) -> None:
        table = _table_element(2, 1, (_cell("범위 오류", 0, 0, end_row=2, row_span=1),))

        with self.assertRaisesRegex(ChunkIntegrityError, "셀 0.*row_span"):
            _chunk(_structure(table))

    def test_실제_열_범위와_다른_column_span을_거부한다(self) -> None:
        table = _table_element(1, 2, (_cell("범위 오류", 0, 0, end_column=2, column_span=1),))

        with self.assertRaisesRegex(ChunkIntegrityError, "셀 0.*column_span"):
            _chunk(_structure(table))

    def test_서로_다른_셀의_격자_위치_중복_점유를_거부한다(self) -> None:
        table = _table_element(1, 1, (_cell("첫 셀", 0, 0), _cell("중복 셀", 0, 0)))

        with self.assertRaisesRegex(ChunkIntegrityError, r"셀 1와 셀 0.*\(0, 0\)"):
            _chunk(_structure(table))

    def test_표_격자의_미표현_슬롯에_셀을_만들지_않는다(self) -> None:
        table = _table_element(1, 2, (_cell("관측된 셀", 0, 0),))

        chunk = _chunk(_structure(table))[0]

        self.assertEqual(len(table.table.cells), 1)
        self.assertEqual(len(chunk.table_row.cells), 1)
        self.assertNotIn("열 2", chunk.text)

    def test_0행_0열_표를_거부한다(self) -> None:
        with self.assertRaisesRegex(ChunkIntegrityError, "row_count"):
            _chunk(_structure(_table_element(0, 0, ())))

    def test_0행_양수_열_표를_거부한다(self) -> None:
        with self.assertRaisesRegex(ChunkIntegrityError, "row_count"):
            _chunk(_structure(_table_element(0, 2, ())))

    def test_양수_행_0열_표를_거부한다(self) -> None:
        with self.assertRaisesRegex(ChunkIntegrityError, "column_count"):
            _chunk(_structure(_table_element(1, 0, ())))

    def test_정상_1행_표는_청크_하나를_만든다(self) -> None:
        chunks = _chunk(_structure(_table_element(1, 1, (_cell("값", 0, 0),))))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].table_row.row_index, 0)

    def test_표_행의_생성_방식을_agentic으로_변조하면_거부한다(self) -> None:
        structure = _structure(_table_element(1, 1, (_cell("값", 0, 0),)))
        chunks = _chunk(structure)
        tampered = (replace(chunks[0], generation_method="agentic"),)

        with self.assertRaises(ChunkIntegrityError):
            _validate_chunks(structure, tampered)

    def test_표_행의_모델_상태를_succeeded로_변조하면_거부한다(self) -> None:
        structure = _structure(_table_element(1, 1, (_cell("값", 0, 0),)))
        chunks = _chunk(structure)
        tampered = (replace(chunks[0], model_status="succeeded"),)

        with self.assertRaises(ChunkIntegrityError):
            _validate_chunks(structure, tampered)

    def test_표_행의_모델_시도_횟수를_변조하면_거부한다(self) -> None:
        structure = _structure(_table_element(1, 1, (_cell("값", 0, 0),)))
        chunks = _chunk(structure)
        tampered = (replace(chunks[0], model_attempts=1),)

        with self.assertRaises(ChunkIntegrityError):
            _validate_chunks(structure, tampered)

    def test_3행_표는_행별_독립_청크_세_개를_만든다(self) -> None:
        table = _table_element(
            3, 1, (_cell("상속포기", 0, 0), _cell("한정승인", 1, 0), _cell("신청기한", 2, 0))
        )
        model = _MockChatModel(())

        chunks = _chunk(_structure(table), model)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(model.calls, 0)
        self.assertEqual([chunk.table_row.row_index for chunk in chunks], [0, 1, 2])
        self.assertEqual(
            [chunk.element_ids for chunk in chunks],
            [("e000001:r000001",), ("e000001:r000002",), ("e000001:r000003",)],
        )
        self.assertEqual([chunk.table_id for chunk in chunks], ["e000001"] * 3)

    def test_한_행의_여러_셀과_원문값을_한_청크에_보존한다(self) -> None:
        table = _table_element(1, 2, (_cell("항목", 0, 0), _cell("내용", 0, 1)))

        chunks = _chunk(_structure(table))
        row = chunks[0].table_row

        self.assertEqual(len(chunks), 1)
        self.assertEqual([use.cell.text for use in row.cells], ["항목", "내용"])
        self.assertTrue(all(use.relation == "source" for use in row.cells))

    def test_표_헤더행도_독립된_실제_행으로_남고_데이터행에_참조된다(self) -> None:
        table = _table_element(
            2,
            2,
            (
                _cell("항목", 0, 0, column_header=True),
                _cell("내용", 0, 1, column_header=True),
                _cell("한정승인", 1, 0),
                _cell("상속재산 범위에서 책임", 1, 1),
            ),
        )

        chunks = _chunk(_structure(table))

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].table_row.is_header)
        self.assertFalse(chunks[1].table_row.is_header)
        self.assertEqual(chunks[1].table_row.header_cell_indexes, (0, 1))
        self.assertIn("[표 헤더 참조]", chunks[1].text)
        self.assertIn("항목", chunks[1].text)
        self.assertIn("내용", chunks[1].text)
        expected_hash = hashlib.sha256('["항목","내용"]'.encode()).hexdigest()
        self.assertEqual(chunks[0].table_row.original_row_sha256, expected_hash)

    def test_다단_헤더행은_앞선_세로_병합_헤더를_검색_텍스트에_참조한다(self) -> None:
        table = _table_element(
            3,
            2,
            (
                _cell("상위 분류", 0, 0, end_row=2, row_span=2, column_header=True),
                _cell("세부 항목", 1, 1, column_header=True),
                _cell("신청기한", 2, 1),
            ),
        )

        chunks = _chunk(_structure(table))
        second_header_row = chunks[1]

        self.assertTrue(second_header_row.table_row.is_header)
        self.assertIn("[표 헤더 참조]", second_header_row.text)
        self.assertIn("상위 분류", second_header_row.text)
        self.assertIn("세부 항목", second_header_row.text)

    def test_빈_셀은_삭제하거나_대체하지_않는다(self) -> None:
        table = _table_element(1, 2, (_cell("값", 0, 0), _cell("", 0, 1)))

        chunks = _chunk(_structure(table))

        self.assertEqual(len(chunks), 1)
        self.assertEqual([use.cell.text for use in chunks[0].table_row.cells], ["값", ""])
        self.assertIn("[열 2] ", chunks[0].text)

    def test_가로_병합_범위와_행열_인덱스를_보존한다(self) -> None:
        merged = _cell("통합 헤더", 0, 0, end_column=2, column_span=2, column_header=True)
        table = _table_element(1, 2, (merged,))

        chunk = _chunk(_structure(table))[0]

        self.assertEqual(chunk.table_row.cells[0].cell, merged)
        self.assertEqual((merged.start_row, merged.end_row, merged.row_span), (0, 1, 1))
        self.assertEqual((merged.start_column, merged.end_column, merged.column_span), (0, 2, 2))

    def test_세로_병합_텍스트는_원본행에만_소유되고_후속행은_참조한다(self) -> None:
        merged = _cell("공통 분류", 0, 0, end_row=2, row_span=2, row_header=True)
        table = _table_element(
            2,
            2,
            (merged, _cell("값", 0, 1), _cell("첫째", 1, 1)),
        )

        chunks = _chunk(_structure(table))
        first_row, second_row = (chunk.table_row for chunk in chunks)
        merged_ref = next(use for use in second_row.cells if use.cell_index == 0)

        self.assertEqual(merged_ref.relation, "merged_reference")
        self.assertIsNone(merged_ref.cell)
        self.assertEqual(
            (merged_ref.start_row, merged_ref.end_row, merged_ref.row_span),
            (0, 2, 2),
        )
        self.assertEqual((merged_ref.start_column, merged_ref.end_column), (0, 1))
        self.assertEqual(first_row.cells[0].cell.text, "공통 분류")
        self.assertIn("[열 1 병합 참조: 원본 행 1", chunks[1].text)
        self.assertIn("공통 분류", chunks[1].text)
        expected_hash = hashlib.sha256('["첫째"]'.encode()).hexdigest()
        self.assertEqual(second_row.original_row_sha256, expected_hash)

    def test_모든_행_청크로_원본_표_DTO를_복원한다(self) -> None:
        cells = (
            _cell("분류", 0, 0, end_row=2, row_span=2, row_header=True),
            _cell("항목", 0, 1, column_header=True),
            _cell("상속포기", 1, 1),
        )
        table_element = _table_element(2, 2, cells)

        chunks = _chunk(_structure(table_element))
        row_chunks = [chunk.table_row for chunk in chunks]
        restored_cells = {
            use.cell_index: use.cell
            for row in row_chunks
            for use in row.cells
            if use.relation == "source"
        }
        restored_indexes = tuple(sorted(restored_cells))

        self.assertEqual(restored_indexes, tuple(range(len(cells))))
        self.assertEqual(tuple(restored_cells[index] for index in restored_indexes), cells)
        self.assertEqual([row.row_index for row in row_chunks], [0, 1])
        self.assertEqual((row_chunks[0].row_count, row_chunks[0].column_count), (2, 2))

    def test_행_512토큰_초과도_분할하지_않고_초과_상태를_표시한다(self) -> None:
        table = _table_element(1, 1, (_cell("긴 행", 0, 0),))

        chunks = _chunk(_structure(table), count_tokens=lambda _text: 600)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].token_count, 600)
        self.assertTrue(chunks[0].over_target)

    def test_동일_행은_결정적_ID를_만들고_값_변경은_해시와_ID를_바꾼다(self) -> None:
        first_structure = _structure(_table_element(1, 1, (_cell("값 A", 0, 0),)))
        same_structure = _structure(_table_element(1, 1, (_cell("값 A", 0, 0),)))
        changed_structure = _structure(_table_element(1, 1, (_cell("값 B", 0, 0),)))

        first = _chunk(first_structure)[0]
        same = _chunk(same_structure)[0]
        changed = _chunk(changed_structure)[0]

        self.assertEqual(first.chunk_id, same.chunk_id)
        self.assertEqual(first.content_sha256, same.content_sha256)
        self.assertNotEqual(first.chunk_id, changed.chunk_id)
        self.assertNotEqual(first.content_sha256, changed.content_sha256)

    def test_셀_병합_구조가_변경되면_Chunk_ID가_바뀐다(self) -> None:
        single_cell = _structure(_table_element(1, 2, (_cell("헤더", 0, 0),)))
        merged_cell = _structure(
            _table_element(1, 2, (_cell("헤더", 0, 0, end_column=2, column_span=2),))
        )

        first = _chunk(single_cell)[0]
        changed = _chunk(merged_cell)[0]

        self.assertNotEqual(first.chunk_id, changed.chunk_id)

    def test_self_ref가_없는_서로_다른_표의_행_ID는_충돌하지_않는다(self) -> None:
        structure = _structure(
            _table_element(1, 1, (_cell("첫 표", 0, 0),), self_ref=None),
            _table_element(1, 1, (_cell("둘째 표", 0, 0),), self_ref=None),
        )

        chunks = _chunk(structure)

        self.assertEqual([chunk.table_id for chunk in chunks], ["e000001", "e000002"])
        self.assertNotEqual(chunks[0].element_ids, chunks[1].element_ids)

    def test_실제_셀_텍스트를_확인할_수_없으면_빈문자열로_대체하지_않고_실패한다(self) -> None:
        unresolved_cell = _cell("", 0, 0)
        # Parser DTO는 text를 str로 선언하지만, 경계의 손상 입력을 방어하는 분기를 시험한다.
        object.__setattr__(unresolved_cell, "text", None)
        table = _table_element(1, 1, (unresolved_cell,))

        with self.assertRaises(UnresolvedCellTextError):
            _chunk(_structure(table))

    def test_표_완전성_미검증과_위치_미검증을_청킹_실패와_구분한다(self) -> None:
        table = _table_element(1, 1, (_cell("관측된 셀", 0, 0),))
        structure = _structure(
            table,
            unverified_items=(
                UnverifiedItem(
                    self_ref=table.self_ref,
                    kind="table_completeness",
                    reason="원본 표 전체와 비교하지 못함",
                ),
                UnverifiedItem(
                    self_ref=table.self_ref,
                    kind="location",
                    reason="위치 좌표 없음",
                ),
            ),
        )

        chunks = _chunk(structure)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].table_row.completeness_status, "unverified")
        self.assertEqual(chunks[0].locations[0].status, "unverified")
        self.assertEqual(chunks[0].model_status, "not_used")

    def test_원본_행_누락과_중복을_무결성_검증에서_감지한다(self) -> None:
        structure = _structure(_table_element(2, 1, (_cell("첫 행", 0, 0), _cell("둘째 행", 1, 0))))
        chunks = _chunk(structure)

        with self.assertRaises(ChunkIntegrityError):
            validate_chunk_integrity(
                structure,
                chunks[:1],
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
            )
        with self.assertRaises(ChunkIntegrityError):
            validate_chunk_integrity(
                structure,
                (chunks[0], chunks[0]),
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
            )

    def test_표_청크에_위치와_provenance를_보존한다(self) -> None:
        location = _location("verified")
        table = _table_element(1, 1, (_cell("값", 0, 0),), location=location)

        chunk = _chunk(_structure(table))[0]

        self.assertEqual(chunk.locations, (location,))
        self.assertEqual(chunk.locations[0].provenance[0].charspan, (7, 19))
        self.assertEqual(chunk.table_row.completeness_status, "unverified")


class ChunkingModelProviderTests(unittest.TestCase):
    def test_ollama_설정으로_모델을_생성한다(self) -> None:
        settings = chunking_model.load_chunking_model_settings(
            {
                "RAG_CHUNKING_PROVIDER": "ollama",
                "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
                "RAG_CHUNKING_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            }
        )
        model = _MockChatModel(())
        ollama_factory = Mock(return_value=model)

        result = chunking_model.create_chunking_model(settings, ollama_factory=ollama_factory)

        self.assertIs(result, model)
        ollama_factory.assert_called_once_with(
            model="qwen3:4b-instruct", base_url="http://127.0.0.1:11434"
        )

    def test_gemini_설정은_RAG_인증값을_명시적으로_전달한다(self) -> None:
        settings = chunking_model.load_chunking_model_settings(
            {
                "RAG_CHUNKING_PROVIDER": "gemini",
                "RAG_CHUNKING_MODEL": "gemini-2.5-flash",
                "RAG_CHUNKING_GEMINI_API_KEY": "rag-secret",
            }
        )
        model = _MockChatModel(())
        gemini_factory = Mock(return_value=model)

        result = chunking_model.create_chunking_model(settings, gemini_factory=gemini_factory)

        self.assertIsInstance(result, BaseChatModel)
        self.assertIs(result.inner_model, model)
        gemini_factory.assert_called_once_with(model="gemini-2.5-flash", api_key="rag-secret")

    def test_선택하지_않은_공급자_생성자를_호출하지_않는다(self) -> None:
        settings = chunking_model.load_chunking_model_settings(
            {"RAG_CHUNKING_PROVIDER": "ollama", "RAG_CHUNKING_MODEL": "qwen3:4b-instruct"}
        )
        ollama_factory = Mock(return_value=_MockChatModel(()))
        gemini_factory = Mock(return_value=_MockChatModel(()))

        chunking_model.create_chunking_model(
            settings, ollama_factory=ollama_factory, gemini_factory=gemini_factory
        )

        ollama_factory.assert_called_once()
        gemini_factory.assert_not_called()

    def test_누락되거나_호환되지_않는_공급자_설정을_거부한다(self) -> None:
        invalid_settings = (
            {},
            {"RAG_CHUNKING_PROVIDER": "groq", "RAG_CHUNKING_MODEL": "some-model"},
            {"RAG_CHUNKING_PROVIDER": "ollama"},
            {"RAG_CHUNKING_PROVIDER": "gemini", "RAG_CHUNKING_MODEL": "qwen3:4b"},
        )

        for environment in invalid_settings:
            with (
                self.subTest(environment=environment),
                self.assertRaises(chunking_model.ChunkingModelConfigurationError),
            ):
                chunking_model.load_chunking_model_settings(environment)

    def test_기존_Gemini_변수로_RAG_인증을_대체하지_않는다(self) -> None:
        with self.assertRaises(chunking_model.ChunkingModelConfigurationError) as raised:
            chunking_model.load_chunking_model_settings(
                {
                    "RAG_CHUNKING_PROVIDER": "gemini",
                    "RAG_CHUNKING_MODEL": "gemini-2.5-flash",
                    "GEMINI_API_KEY": "legacy-secret",
                    "LLM_PROVIDER": "gemini",
                }
            )

        self.assertNotIn("legacy-secret", str(raised.exception))

    def test_ollama는_Gemini_인증값이_없어도_생성한다(self) -> None:
        settings = chunking_model.load_chunking_model_settings(
            {"RAG_CHUNKING_PROVIDER": "ollama", "RAG_CHUNKING_MODEL": "qwen3:4b-instruct"}
        )
        factory = Mock(return_value=_MockChatModel(()))

        chunking_model.create_chunking_model(settings, ollama_factory=factory)

        factory.assert_called_once()

    def test_설정된_모델을_기존_chunk_document에_주입한다(self) -> None:
        model = _MockChatModel((_response(("e000001",)),))
        structure = _structure(_element("본문"))

        async def run() -> tuple[Any, ...]:
            return await service.chunk_document_with_config(
                structure,
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
                environ={
                    "RAG_CHUNKING_PROVIDER": "ollama",
                    "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
                },
                model_factory=lambda _: model,
            )

        chunks = asyncio.run(run())

        self.assertEqual(model.calls, 1)
        self.assertEqual(chunks[0].generation_method, "agentic")

    def test_HTTP_429에서_다른_공급자를_생성하거나_전환하지_않는다(self) -> None:
        model = _MockChatModel((_RateLimitError("429 rate limited"),))
        gemini_factory = Mock(return_value=_MockChatModel(()))

        async def run() -> tuple[Any, ...]:
            return await service.chunk_document_with_config(
                _structure(_element("본문")),
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
                environ={
                    "RAG_CHUNKING_PROVIDER": "ollama",
                    "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
                },
                model_factory=_configured_model_factory(
                    ollama_factory=lambda **_: model,
                    gemini_factory=gemini_factory,
                ),
            )

        chunks = asyncio.run(run())

        self.assertEqual(model.calls, 1)
        gemini_factory.assert_not_called()
        self.assertTrue(chunks[0].fallback_used)
        self.assertIn("429", chunks[0].model_failure)

    def test_표_행_청킹은_생성된_모델을_호출하지_않는다(self) -> None:
        model = _MockChatModel(())

        async def run() -> tuple[Any, ...]:
            return await service.chunk_document_with_config(
                _structure(_table_element(1, 1, (_cell("값", 0, 0),))),
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
                environ={
                    "RAG_CHUNKING_PROVIDER": "ollama",
                    "RAG_CHUNKING_MODEL": "qwen3:4b-instruct",
                },
                model_factory=lambda _: model,
            )

        chunks = asyncio.run(run())

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].kind, "table_row")
        self.assertEqual(chunks[0].model_status, "not_used")
        self.assertEqual(model.calls, 0)

    def test_초기화_오류에_인증값을_노출하지_않는다(self) -> None:
        secret = "rag/a+b"
        encoded = quote(secret, safe="")
        mixed_case = encoded.replace("%2F", "%2f")
        settings = chunking_model.load_chunking_model_settings(
            {
                "RAG_CHUNKING_PROVIDER": "gemini",
                "RAG_CHUNKING_MODEL": "gemini-2.5-flash",
                "RAG_CHUNKING_GEMINI_API_KEY": secret,
            }
        )
        provider_error = RuntimeError(
            f"bad key: {secret} | {encoded} | {encoded.lower()} | {mixed_case}"
        )
        provider_error.__cause__ = RuntimeError(f"wrapped constructor error contains {encoded}")
        log_output = io.StringIO()
        log_handler = logging.StreamHandler(log_output)
        root_logger = logging.getLogger()
        original_log_level = root_logger.level
        root_logger.addHandler(log_handler)
        root_logger.setLevel(logging.DEBUG)

        try:
            with self.assertRaises(chunking_model.ChunkingModelInitializationError) as raised:
                chunking_model.create_chunking_model(
                    settings,
                    gemini_factory=Mock(side_effect=provider_error),
                )
        finally:
            root_logger.removeHandler(log_handler)
            root_logger.setLevel(original_log_level)
            log_handler.close()

        failure = raised.exception
        exposed_text = (
            str(failure) + "".join(traceback.format_exception(failure)) + log_output.getvalue()
        )
        for secret_form in (secret, encoded, encoded.lower(), mixed_case):
            self.assertNotIn(secret_form, exposed_text)
        self.assertIsNone(failure.__cause__)
        self.assertIsNone(failure.__context__)
        self.assertNotIn(secret, repr(settings))

    def test_존재하지_않는_Gemini_모델의_API_오류를_fallback_결과에_남긴다(self) -> None:
        model = _MockChatModel((RuntimeError("404 model not found"),) * 4)

        async def run() -> tuple[Any, ...]:
            return await service.chunk_document_with_config(
                _structure(_element("본문")),
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
                environ={
                    "RAG_CHUNKING_PROVIDER": "gemini",
                    "RAG_CHUNKING_MODEL": "gemini-not-real",
                    "RAG_CHUNKING_GEMINI_API_KEY": "rag-secret",
                },
                model_factory=_configured_model_factory(gemini_factory=lambda **_: model),
            )

        chunks = asyncio.run(run())

        self.assertEqual(model.calls, 4)
        self.assertEqual(chunks[0].model_status, "failed")
        self.assertIn("404 model not found", chunks[0].model_failure)

    def test_Gemini_실행_오류의_인증값을_fallback_메타데이터에서_숨긴다(self) -> None:
        secret = "rag/a+b"
        encoded = quote(secret, safe="")
        mixed_case = encoded.replace("%2F", "%2f")
        provider_error = _GoogleRateLimitError(secret)
        self.assertEqual(provider_error.status, "RESOURCE_EXHAUSTED")
        self.assertIsNone(getattr(provider_error, "status_code", None))
        self.assertIsNone(getattr(provider_error.__cause__, "code", None))
        model = _MockChatModel((provider_error,))
        ollama_factory = Mock(return_value=_MockChatModel(()))

        async def run() -> tuple[Any, ...]:
            return await service.chunk_document_with_config(
                _structure(_element("본문")),
                source_id="guide-1",
                version="v1",
                count_tokens=_tokens,
                environ={
                    "RAG_CHUNKING_PROVIDER": "gemini",
                    "RAG_CHUNKING_MODEL": "gemini-2.5-flash",
                    "RAG_CHUNKING_GEMINI_API_KEY": secret,
                },
                model_factory=_configured_model_factory(
                    gemini_factory=lambda **_: model,
                    ollama_factory=ollama_factory,
                ),
            )

        chunks = asyncio.run(run())

        self.assertEqual(chunks[0].model_status, "failed")
        self.assertEqual(chunks[0].model_attempts, 1)
        self.assertTrue(chunks[0].fallback_used)
        self.assertEqual(chunks[0].generation_method, "deterministic")
        for secret_form in (secret, encoded, encoded.lower(), mixed_case):
            self.assertNotIn(secret_form, chunks[0].model_failure)
        self.assertIn("[REDACTED]", chunks[0].model_failure)
        self.assertIn("HTTP 429", chunks[0].model_failure)
        self.assertEqual(model.calls, 1)
        ollama_factory.assert_not_called()

    def test_Gemini_중첩된_숫자_code_429도_정상화한다(self) -> None:
        secret = "rag/a+b"
        provider_error = RuntimeError(f"wrapped provider failure: {secret}")
        provider_error.__cause__ = _RateLimitCause(f"HTTP 429: {secret}")
        inner_model = _MockChatModel((provider_error,))
        model = chunking_model.create_chunking_model(
            chunking_model.ChunkingModelSettings(
                provider="gemini",
                model="gemini-2.5-flash",
                gemini_api_key=secret,
            ),
            gemini_factory=lambda **_: inner_model,
        )

        with self.assertRaises(RuntimeError) as raised:
            asyncio.run(model._agenerate(messages=[]))

        self.assertEqual(raised.exception.status_code, 429)
        self.assertNotIn(secret, str(raised.exception))
        self.assertEqual(inner_model.calls, 1)

    def test_Gemini_실행_예외_traceback에_원본_키와_예외_체인을_남기지_않는다(self) -> None:
        secret = "rag/a+b"
        encoded = quote(secret, safe="")
        mixed_case = encoded.replace("%2F", "%2f")
        inner_model = _MockChatModel((_GoogleRateLimitError(secret),))
        model = chunking_model.create_chunking_model(
            chunking_model.ChunkingModelSettings(
                provider="gemini",
                model="gemini-2.5-flash",
                gemini_api_key=secret,
            ),
            gemini_factory=lambda **_: inner_model,
        )
        log_output = io.StringIO()
        log_handler = logging.StreamHandler(log_output)
        root_logger = logging.getLogger()
        original_log_level = root_logger.level
        root_logger.addHandler(log_handler)
        root_logger.setLevel(logging.DEBUG)

        try:
            with self.assertRaises(RuntimeError) as raised:
                asyncio.run(model._agenerate(messages=[]))
        finally:
            root_logger.removeHandler(log_handler)
            root_logger.setLevel(original_log_level)
            log_handler.close()

        failure = raised.exception
        exposed_text = (
            str(failure) + "".join(traceback.format_exception(failure)) + log_output.getvalue()
        )
        for secret_form in (secret, encoded, encoded.lower(), mixed_case):
            self.assertNotIn(secret_form, exposed_text)
        self.assertEqual(failure.status_code, 429)
        self.assertIsNone(failure.__cause__)
        self.assertIsNone(failure.__context__)
        self.assertEqual(inner_model.calls, 1)

    def test_모듈_import은_공급자_또는_llm_패키지를_불러오지_않는다(self) -> None:
        imported: list[str] = []
        original_import = builtins.__import__

        def track_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.startswith(
                ("langchain_google_genai", "langchain_ollama", "llm", "starter_llm")
            ):
                imported.append(name)
            return original_import(name, *args, **kwargs)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("builtins.__import__", side_effect=track_import),
        ):
            importlib.reload(chunking_model)
            importlib.reload(service)

        self.assertEqual(imported, [])


if __name__ == "__main__":
    unittest.main()
