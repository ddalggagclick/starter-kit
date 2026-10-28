# 담당: [D] | 책임: 공식 안내자료 적재·게시 관리자 CLI.
# PRD: E6 / 스토리 6-2 / 태스크 6-2-3 (관리자 적재 흐름 지원)
# 구현할 기능: 명시적 명령으로 문서를 적재하고 검수·게시 상태를 관리한다.
# 완료 기준: 게시 승인 전 자료가 검색 대상이 되지 않는다.
# 제한사항: 서버 앱 시작 시 자동 적재·색인을 실행하지 않는다.

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from starter_rag.ingestion.review import (
    ReviewError,
    apply_corrections,
    approve_review,
    read_review,
)

Prompt = Callable[[str], str]


def _save_draft(path: Path, report: dict) -> None:
    """Persist edits atomically; any edit invalidates a prior approval."""
    report["approval"] = {"state": "draft", "content_sha256": None}
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            temporary.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _ask_int(question: str, *, lower: int, upper: int, prompt: Prompt) -> int:
    text = prompt(question).strip()
    try:
        answer = int(text)
    except ValueError as exc:
        raise ReviewError("정수를 입력하세요.") from exc
    if not lower <= answer <= upper:
        raise ReviewError(f"{lower}~{upper} 범위를 입력하세요.")
    return answer


def _cell_lines(correction: dict) -> None:
    print("\n[표 셀 목록] (행·열 인덱스는 0부터 시작)")
    for index, cell in enumerate(correction["replacement_cells"]):
        text = cell["text"].replace("\n", " ")
        # A long cell is shown in full to support exact-text selection.
        print(
            f"  [{index}] 행 {cell['start_row']}~{cell['end_row'] - 1}, "
            f"열 {cell['start_column']}~{cell['end_column'] - 1}: {text}"
        )
    if correction["detached_notes"]:
        print("[표 밖으로 분리한 문구]")
        for idx, note in enumerate(correction["detached_notes"]):
            print(f"  ({idx + 1}) {note}")


def _split_cell(correction: dict, *, selected: int, phrase: str) -> None:
    """Detach an exact span, keeping every original non-whitespace character."""
    cells = correction["replacement_cells"]
    if not 0 <= selected < len(cells):
        raise ReviewError("셀 번호가 올바르지 않습니다.")
    if not phrase or not phrase.strip():
        raise ReviewError("분리할 원문을 입력하세요.")
    old = cells[selected]["text"]
    if phrase not in old:
        raise ReviewError("선택한 문구가 해당 셀의 원문과 정확히 일치하지 않습니다.")
    remaining = old.replace(phrase, "", 1).strip()
    origin = cells[selected].get("_origin_index", selected)
    if remaining:
        cells[selected]["text"] = remaining
    else:
        cells.pop(selected)
    correction["detached_notes"].append(phrase.strip())
    if origin not in correction["acknowledged_cell_indexes"]:
        correction["acknowledged_cell_indexes"].append(origin)
    correction["action"] = "replace"


def _move_cell(correction: dict, *, selected: int, bounds: tuple[int, int, int, int]) -> None:
    cells = correction["replacement_cells"]
    if not 0 <= selected < len(cells):
        raise ReviewError("셀 번호가 올바르지 않습니다.")
    sr, er, sc, ec = bounds
    if not (0 <= sr < er <= correction["row_count"] and 0 <= sc < ec <= correction["column_count"]):
        raise ReviewError("표 행·열 범위를 확인하세요. end 값은 마지막 인덱스보다 1 커야 합니다.")
    cells[selected].update(
        start_row=sr,
        end_row=er,
        start_column=sc,
        end_column=ec,
        row_span=er - sr,
        column_span=ec - sc,
    )
    correction["action"] = "replace"


def _recover_empty_table(correction: dict, *, prompt: Prompt) -> None:
    """Collect a human transcription when Docling returned a 0x0 PDF table."""
    print("Docling이 이 표의 셀을 추출하지 못했습니다. 원본 PDF 페이지를 보며 직접 입력하세요.")
    rows = _ask_int("원본 표 행 수: ", lower=1, upper=100, prompt=prompt)
    columns = _ask_int("원본 표 열 수: ", lower=1, upper=100, prompt=prompt)
    count = _ask_int("문구가 있는 셀 수: ", lower=1, upper=rows * columns, prompt=prompt)
    cells: list[dict] = []
    for index in range(count):
        value = prompt(f"셀 {index + 1} 원문: ").strip()
        if not value:
            raise ReviewError("복원 셀 원문은 비어 있을 수 없습니다.")
        sr = _ask_int("시작 행: ", lower=0, upper=rows - 1, prompt=prompt)
        er = _ask_int("끝 행(미포함): ", lower=sr + 1, upper=rows, prompt=prompt)
        sc = _ask_int("시작 열: ", lower=0, upper=columns - 1, prompt=prompt)
        ec = _ask_int("끝 열(미포함): ", lower=sc + 1, upper=columns, prompt=prompt)
        cells.append(
            {
                "text": value,
                "start_row": sr,
                "end_row": er,
                "start_column": sc,
                "end_column": ec,
                "row_span": er - sr,
                "column_span": ec - sc,
                "column_header": False,
                "row_header": False,
                "row_section": False,
                "fillable": False,
                "self_ref": None,
                "bbox": None,
            }
        )
    if prompt("표 문구와 위치를 원본 PDF 페이지에서 확인했습니까? [y/N]: ").strip().lower() not in {
        "y",
        "yes",
    }:
        raise ReviewError("원본 PDF의 시각적 대조가 필요합니다.")
    correction.update(
        action="recover_from_pdf",
        row_count=rows,
        column_count=columns,
        replacement_cells=cells,
        visual_confirmation=True,
    )


def assist_review(review_file: Path, *, prompt: Prompt | None = None) -> bool:
    """Interactive edit/validate/approve loop. Return True when approved."""
    if prompt is None:
        prompt = input
    try:
        report = json.loads(review_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewError("검토 파일을 읽을 수 없습니다.") from exc
    if not isinstance(report, dict) or not isinstance(report.get("issues"), list):
        raise ReviewError("검토 파일 형식이 올바르지 않습니다.")
    if (report.get("approval") or {}).get("state") == "approved":
        # Validating approval also validates the complete original snapshot.
        read_review(review_file, require_approved=True)
        print("이미 승인한 검토 파일입니다. 수정하려면 새 검토 파일을 생성하세요.")
        return True
    issues = report["issues"]
    if not issues:
        print("표 구조 충돌이 발견되지 않았습니다. 원본과 파싱 결과를 확인한 뒤 승인하세요.")
    for issue in issues:
        table_id = issue["table_id"]
        correction = next((c for c in report["corrections"] if c["table_id"] == table_id), None)
        if correction is None or correction.get("row_count") is None:
            raise ReviewError(f"{table_id}: 표 원본이 없어 대화형 편집을 진행할 수 없습니다.")
        for i, cell in enumerate(correction["replacement_cells"]):
            cell.setdefault("_origin_index", i)
        print(f"\n[검토] 표 {table_id} / PDF 페이지 {issue.get('page_numbers', [])}")
        print(
            f"충돌: {issue.get('collisions', [])}; 유효하지 않은 셀: {issue.get('invalid_cells', [])}"
        )
        if correction["row_count"] == 0 and correction["column_count"] == 0:
            if prompt("빈 표를 PDF에서 복원하려면 1, 저장 후 중단하려면 0: ").strip() != "1":
                _save_draft(review_file, report)
                return False
            try:
                _recover_empty_table(correction, prompt=prompt)
                _save_draft(review_file, report)
                apply_corrections(report)
            except (ReviewError, ValueError, KeyError) as exc:
                print(f"검토 필요: {exc}")
                _save_draft(review_file, report)
                return False
            continue
        while True:
            _cell_lines(correction)
            print("\n1: 셀의 문구를 표 밖 주의 문구로 분리")
            print("2: 셀의 행·열 위치/병합 범위 수정")
            print("3: 분리된 주의 문구를 한 문단으로 연결")
            print("4: 수정 구조 검사")
            print("5: 다음 단계로 진행")
            print("0: 저장하고 중단 (나중에 review assist로 재개)")
            choice = prompt("선택 [0~5]: ").strip()
            if choice == "0":
                _save_draft(review_file, report)
                return False
            if choice == "5":
                correction["action"] = "replace"
                _save_draft(review_file, report)
                break
            try:
                if choice == "1":
                    selected = _ask_int(
                        "문구를 분리할 셀 번호: ",
                        lower=0,
                        upper=len(correction["replacement_cells"]) - 1,
                        prompt=prompt,
                    )
                    phrase = prompt("분리할 정확한 원문 (셀 전체 또는 일부): ")
                    _split_cell(correction, selected=selected, phrase=phrase)
                    _save_draft(review_file, report)
                elif choice == "2":
                    selected = _ask_int(
                        "좌표를 수정할 셀 번호: ",
                        lower=0,
                        upper=len(correction["replacement_cells"]) - 1,
                        prompt=prompt,
                    )
                    count_rows, count_cols = correction["row_count"], correction["column_count"]
                    sr = _ask_int("시작 행: ", lower=0, upper=count_rows - 1, prompt=prompt)
                    er = _ask_int("끝 행(미포함): ", lower=sr + 1, upper=count_rows, prompt=prompt)
                    sc = _ask_int("시작 열: ", lower=0, upper=count_cols - 1, prompt=prompt)
                    ec = _ask_int("끝 열(미포함): ", lower=sc + 1, upper=count_cols, prompt=prompt)
                    _move_cell(correction, selected=selected, bounds=(sr, er, sc, ec))
                    _save_draft(review_file, report)
                elif choice == "3":
                    notes = correction["detached_notes"]
                    if not notes:
                        raise ReviewError("분리한 문구가 없습니다.")
                    # Joining is whitespace-only; it does not drop text.
                    correction["detached_notes"] = [" ".join(notes)]
                    correction["action"] = "replace"
                    _save_draft(review_file, report)
                elif choice == "4":
                    correction["action"] = "replace"
                    _save_draft(review_file, report)
                    apply_corrections(report)
                    print("PASS: 현재 보정 구조와 텍스트 보존 검사 통과")
                else:
                    print("0~5 중 하나를 입력하세요.")
            except (ReviewError, ValueError, KeyError) as exc:
                print(f"검토 필요: {exc}")
    try:
        output = apply_corrections(report)
    except (ReviewError, KeyError, ValueError) as exc:
        print(f"수정 검증 실패: {exc}")
        print(
            f"작업 내용을 저장했습니다. 다음 명령으로 재개하세요: starter-rag review assist '{review_file}'"
        )
        return False
    print(f"\n보정 검증 성공: {len(output.elements)}개 요소, 문제 표 {len(issues)}개 검토")
    print("원본 PDF를 열어 셀과 분리된 주의 문구가 정확한지 최종 확인하세요.")
    approved = prompt("원본 PDF 대조를 완료하고 승인합니까? [y/N]: ").strip().lower()
    if approved not in {"y", "yes"}:
        _save_draft(review_file, report)
        return False
    approve_review(review_file)
    print(f"승인 완료: {review_file}")
    return True
