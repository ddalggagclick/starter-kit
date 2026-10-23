"""외부 모델이나 DB 없이 Source_v2 단일 시트를 검증한다."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from starter_rag.ingestion.parser import APPROVED, HEADERS, SourceV2Error, read_source_units


def workbook_fixture(
    path: Path,
    *,
    bad_url: bool = False,
    duplicate: bool = False,
    stale_hash: bool = False,
    second_sheet: bool = False,
    unapproved: bool = False,
    missing_unit_id: bool = False,
) -> None:
    first = {
        "Unit ID": "" if missing_unit_id else "U-TEST-WITH",
        "Unit 목록 행": "2",
        "절차·주제": "링크 비표시 기관 안내",
        "연결된 기본 카드": "②",
        "공식 URL (내부 출처)": "http://bad.example.org" if bad_url else "https://example.org/info",
        "화면 URL 사용": "표시 금지 / 없음",
        "연결한 링크 행": "30, 53",
        "RAG 인용 발췌 본문 (링크 H열 원문)": "정확한 인용 문구: <문자> & 내용\n\n확인 사항.",
        "투입 조건 (Unit F)": "공식 기관 확인",
        "미확인·유의 (Unit G)": "미확인 상태",
        "공식 원문 위치 메모 (Unit J)": "확인 필요",
        "버전·기준일 (Unit K)": "별도 검증",
        "적재 승인": "검토 중" if unapproved else APPROVED,
        "본문 범위": "발췌",
        "사용 주의": "완결 안내 아님",
        "기관·발행처": "공식 기관",
        "원본 링크 위치": "SU_링크기록(전체)!H30; SU_링크기록(전체)!H53",
    }
    second = {
        "Unit ID": "U-TEST-WITH" if duplicate else "U-TEST-NO",
        "Unit 목록 행": "3",
        "절차·주제": "고객센터 확인 안내",
        "화면 URL 사용": "표시 금지 / 없음",
        "연결한 링크 행": "54",
        "RAG 인용 발췌 본문 (링크 H열 원문)": "기관 고객센터에서 확인",
        "투입 조건 (Unit F)": "전화 확인",
        "적재 승인": APPROVED,
        "기관·발행처": "기관",
        "원본 링크 위치": "SU_링크기록(전체)!H54",
    }
    for data in (first, second):
        key = hashlib.sha256(
            (
                data["Unit ID"]
                + "\n"
                + data["RAG 인용 발췌 본문 (링크 H열 원문)"]
                + "\n"
                + data.get("투입 조건 (Unit F)", "")
                + "\n"
                + data.get("미확인·유의 (Unit G)", "")
            ).encode()
        ).hexdigest()
        data["소스 변경키"] = "broken" if stale_hash else key

    def col_label(index: int) -> str:
        chars = ""
        index += 1
        while index:
            index, value = divmod(index - 1, 26)
            chars = chr(ord("A") + value) + chars
        return chars

    def worksheet(values: list[dict[str, str]]) -> str:
        rows = []
        for number, data in enumerate(values, 1):
            columns = []
            for index, header in enumerate(HEADERS):
                text = data.get(header, "")
                if text:
                    columns.append(
                        f'<c r="{col_label(index)}{number}" t="inlineStr">'
                        f"<is><t>{escape(text)}</t></is></c>"
                    )
            rows.append(f'<row r="{number}">{"".join(columns)}</row>')
        return (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>" + "".join(rows) + "</sheetData></worksheet>"
        )

    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="RAG_Unit본문" sheetId="1" r:id="rId1"/>'
        + ('<sheet name="Old" sheetId="2" r:id="rId2"/>' if second_sheet else "")
        + "</sheets></workbook>"
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
        + ('<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>' if second_sheet else "")
        + "</Relationships>"
    )
    with ZipFile(path, "w") as package:
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", relationships)
        package.writestr(
            "xl/worksheets/sheet1.xml", worksheet([dict(zip(HEADERS, HEADERS)), first, second])
        )
        if second_sheet:
            package.writestr("xl/worksheets/sheet2.xml", worksheet([dict(zip(HEADERS, HEADERS))]))


class OneSheetTests(unittest.TestCase):
    def test_원문발췌와비공개내부주소를유지한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "input.xlsx"
            workbook_fixture(workbook)
            units = read_source_units(workbook, enforce_baseline=False)
            self.assertEqual(len(units), 2)
            self.assertEqual(units[0].excerpt, "정확한 인용 문구: <문자> & 내용\n\n확인 사항.")
            self.assertEqual(
                units[0].historical_positions, ("SU_링크기록(전체)!H30", "SU_링크기록(전체)!H53")
            )
            self.assertFalse(units[0].display_link_allowed)
            self.assertEqual(units[0].official_url, "https://example.org/info")
            self.assertIsNone(units[1].official_url)

    def test_유효하지않은주소를거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "invalid.xlsx"
            workbook_fixture(workbook, bad_url=True)
            with self.assertRaisesRegex(SourceV2Error, "HTTPS"):
                read_source_units(workbook, enforce_baseline=False)

    def test_중복유닛을거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "invalid.xlsx"
            workbook_fixture(workbook, duplicate=True)
            with self.assertRaisesRegex(SourceV2Error, "duplicate"):
                read_source_units(workbook, enforce_baseline=False)

    def test_기본검증에서불완전한유닛집합을거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "incomplete.xlsx"
            workbook_fixture(workbook)
            with self.assertRaisesRegex(SourceV2Error, "expected 31 approved Units"):
                read_source_units(workbook)

    def test_승인되지않은유닛을거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "unapproved.xlsx"
            workbook_fixture(workbook, unapproved=True)
            with self.assertRaisesRegex(SourceV2Error, "not approved"):
                read_source_units(workbook, enforce_baseline=False)

    def test_누락된유닛식별자를거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "missing-id.xlsx"
            workbook_fixture(workbook, missing_unit_id=True)
            with self.assertRaisesRegex(SourceV2Error, "missing Unit ID"):
                read_source_units(workbook, enforce_baseline=False)

    def test_본문해시불일치를거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "invalid.xlsx"
            workbook_fixture(workbook, stale_hash=True)
            with self.assertRaisesRegex(SourceV2Error, "content key"):
                read_source_units(workbook, enforce_baseline=False)

    def test_여러시트가있는통합문서를거부한다(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Path(folder) / "invalid.xlsx"
            workbook_fixture(workbook, second_sheet=True)
            with self.assertRaisesRegex(SourceV2Error, "only RAG_Unit본문"):
                read_source_units(workbook, enforce_baseline=False)


if __name__ == "__main__":
    unittest.main()
