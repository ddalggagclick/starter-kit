"""Shared, domain-neutral fixtures for RAG behavior tests."""

from __future__ import annotations

from starter_rag.ingestion.parser import (
    DocumentElement,
    DocumentLocation,
    DocumentStructure,
    TableCellStructure,
    TableRowStructure,
    TableStructure,
)


def hitl_cell(text: str, start_row: int, end_row: int, start_column: int, end_column: int):
    return TableCellStructure(
        text=text,
        start_row=start_row,
        end_row=end_row,
        start_column=start_column,
        end_column=end_column,
        row_span=end_row - start_row,
        column_span=end_column - start_column,
        column_header=False,
        row_header=False,
        row_section=False,
        fillable=False,
        self_ref=None,
        bbox=None,
    )


def hitl_document(*, conflict: bool = True) -> DocumentStructure:
    location = DocumentLocation("verified", (2,), ())
    cells = (
        hitl_cell("Category", 0, 1, 2, 3),
        hitl_cell("Primary entry", 1, 2, 2, 3),
        hitl_cell("Supporting note", 2, 4, 2, 3),
    ) + ((hitl_cell("Separate value", 3, 4, 2, 3),) if conflict else ())
    table = TableStructure(
        row_count=4,
        column_count=3,
        cells=cells,
        rows=tuple(
            TableRowStructure(
                index,
                tuple(
                    cell_index for cell_index, cell in enumerate(cells) if cell.start_row == index
                ),
            )
            for index in range(4)
        ),
    )
    return DocumentStructure(
        source_format="pdf",
        elements=(
            DocumentElement(
                "paragraph",
                "Before the table",
                "Before the table",
                "#/texts/1",
                None,
                location,
                None,
            ),
            DocumentElement("table", None, None, "#/tables/1", None, location, table),
            DocumentElement(
                "paragraph", "After the table", "After the table", "#/texts/2", None, location, None
            ),
        ),
        unverified_items=(),
    )
