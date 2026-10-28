# 담당: [D] | 책임: Evidence의 터미널 표시 형식.
# 구현할 기능: JSON 계약을 바꾸지 않고 기록된 위치와 읽기 쉬운 본문을 표시한다.
# 완료 기준: 제어문자가 터미널에 출력되지 않고 원본 Evidence는 수정되지 않는다.
from __future__ import annotations

import json
import re

from starter_rag.contracts.models import Evidence

_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _safe_text(value: str) -> str:
    return _CONTROLS.sub(" ", value).strip()


def _location_summary(location: str) -> str:
    try:
        data = json.loads(location)
    except (ValueError, TypeError):
        return _safe_text(location) or "위치 미확인"
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return _safe_text(location) or "위치 미확인"
    pages = sorted(
        {
            page
            for item in data
            if isinstance(item, dict)
            for page in item.get("page_numbers", [])
            if type(page) is int
        }
    )
    details: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"page_numbers", "status", "provenance"} or not isinstance(value, str):
                continue
            safe_key = _safe_text(key)
            safe_value = _safe_text(value)
            if safe_key and safe_value:
                details.append(f"{safe_key}: {safe_value}")
    parts = ([f"{page}쪽" for page in pages] if pages else []) + details
    return " · ".join(parts) if parts else "위치 미확인"


def format_evidence(items: tuple[Evidence, ...]) -> str:
    lines: list[str] = []
    for rank, item in enumerate(items, 1):
        readable = _safe_text(item.text)
        location = _location_summary(item.location)
        location_suffix = f" · {location}" if location != "위치 미확인" else ""
        lines.append(f"{rank}. {_safe_text(item.source.title)}{location_suffix}")
        lines.append(
            f"   {_safe_text(item.evidence_id)} · 점수 {item.score:.3f}"
            if item.score is not None
            else f"   {_safe_text(item.evidence_id)}"
        )
        lines.append(readable)
        lines.append("")
    return "\n".join(lines).rstrip()
