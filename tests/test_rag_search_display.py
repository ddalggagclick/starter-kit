"""Readable CLI search output leaves the public Evidence payload untouched."""

from __future__ import annotations

from starter_rag.contracts.models import Evidence, SourceRef
from starter_rag.retrieval.display import format_evidence


def test_기록된_위치만_표시하고_제어문자를_제거한다() -> None:
    item = Evidence(
        evidence_id="chunk-1",
        source=SourceRef("guide", "Sample\x07 guide", None, "Publisher", "v1"),
        text="Section heading\n\x07A sample instruction mentions 제99조.",
        location=(
            '[{"page_numbers": [3], "section": "제3조", "status": "verified", "provenance": []}]'
        ),
        score=0.8,
    )
    output = format_evidence((item,))
    header = output.splitlines()[0]
    assert "3쪽" in header
    assert "section: 제3조" in header
    assert "제99조" not in header
    assert "Section heading" in output
    assert "\x07" not in output
    assert "chunk-1" in output
    assert "Sample  guide" in header
    assert "\x07" in item.text
