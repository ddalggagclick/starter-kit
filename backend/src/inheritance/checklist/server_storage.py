# 담당: [B] | 책임: A17 로그인 사용자의 서버 체크리스트 저장소.
# PRD: E4 / 태스크 4-6-2, 4-5-3, 4-6-3, 5-4-2.
# 구현할 기능: 계정별로 서버 저장 동의와 체크리스트 상태를 저장·조회·삭제한다.
# 완료 기준: 다른 계정 자료에 접근할 수 없고, 동의 철회·탈퇴 시 서버 자료가 지워진다.
# 제한사항: ERD 승인 전이라 메모리 저장소다(재시작하면 사라짐). DB 저장소는 같은 메서드로 교체한다.
"""A17 저장 규칙(2026-10-26 팀 회의 결정).

- 저장 데이터: 프론트(#134) itemStates 모양 그대로. 서버는 내용을 해석하지 않고 계정별로 통째로 저장한다.
- 미동의 조회: 저장 본문 없이 거부(router가 403).
- 충돌: PUT은 전체 덮어쓰기. 서버는 이 기기 기록과 자동으로 합치지 않는다(4-6-3).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine, text

MAX_ITEMS = 20
MAX_BYTES = 64 * 1024


class InvalidItemStates(ValueError):
    pass


@dataclass(frozen=True)
class SavedChecklist:
    item_states: tuple[dict, ...]


# 배열·객체 모양과 크기만 확인한다. 안쪽 필드는 프론트 계약(kind·version)이 책임진다.
def validate_item_states(item_states: object) -> tuple[dict, ...]:
    if not isinstance(item_states, list) or len(item_states) > MAX_ITEMS:
        raise InvalidItemStates
    if not all(isinstance(item, dict) for item in item_states):
        raise InvalidItemStates
    try:
        size = len(json.dumps(item_states, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise InvalidItemStates from None
    if size > MAX_BYTES:
        raise InvalidItemStates
    return tuple(item_states)


class InMemoryServerChecklistStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, SavedChecklist] = {}

    # 동의해서 저장한 기록이 있을 때만 돌려준다. 없으면 None(동의 없음).
    def get(self, user_id: str) -> SavedChecklist | None:
        with self._lock:
            return self._items.get(user_id)

    def put(self, user_id: str, item_states: tuple[dict, ...]) -> SavedChecklist:
        saved = SavedChecklist(item_states)
        with self._lock:
            self._items[user_id] = saved
        return saved

    # 동의 철회·탈퇴. 없어도 같은 결과다.
    def delete(self, user_id: str) -> None:
        with self._lock:
            self._items.pop(user_id, None)


# 메모리 저장소와 DB 저장소가 같은 메서드를 가진다.
class ServerChecklistStore(Protocol):
    def get(self, user_id: str) -> SavedChecklist | None: ...
    def put(self, user_id: str, item_states: tuple[dict, ...]) -> SavedChecklist: ...
    def delete(self, user_id: str) -> None: ...


class PostgresServerChecklistStore:
    """app.server_checklists. 계정당 한 행, itemStates는 JSONB로 통째 저장(전체 덮어쓰기)."""

    def __init__(self, engine: Engine, schema: str = "app") -> None:
        self._engine = engine
        self._s = schema

    def get(self, user_id: str) -> SavedChecklist | None:
        sql = text(f"SELECT item_states FROM {self._s}.server_checklists WHERE user_id = :id")
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"id": user_id}).first()
        return SavedChecklist(tuple(row.item_states)) if row else None

    def put(self, user_id: str, item_states: tuple[dict, ...]) -> SavedChecklist:
        sql = text(
            f"INSERT INTO {self._s}.server_checklists (user_id, item_states, updated_at) "
            "VALUES (:id, CAST(:items AS jsonb), now()) "
            "ON CONFLICT (user_id) DO UPDATE SET item_states = EXCLUDED.item_states, "
            "updated_at = now()"
        )
        payload = json.dumps(list(item_states), ensure_ascii=False)
        with self._engine.begin() as conn:
            conn.execute(sql, {"id": user_id, "items": payload})
        return SavedChecklist(item_states)

    def delete(self, user_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {self._s}.server_checklists WHERE user_id = :id"),
                {"id": user_id},
            )
