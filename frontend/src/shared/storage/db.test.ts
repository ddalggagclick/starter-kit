// Dexie 저장소 단위 테스트(4-2-1, 4-2-2, 4-2-4): 읽기·삭제의 namespace 격리, 체크리스트·대화 삭제 분리, 실패 결과 변환.
// 쓰기는 동의 확인을 거치는 consent.ts에만 있으므로 consent.test.ts에서 검사한다. 여기서는 테이블에 직접 넣어 준비한다.
// fake-indexeddb는 Node에서 IndexedDB 규격을 메모리로 흉내 낸다. 실제 브라우저 차단·용량 동작은 검증하지 않는다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureState } from "@/shared/state/inheritance-store"
import {
  accountNamespace,
  type ChecklistSnapshot,
  type ConversationRecord,
  deleteAllConversations,
  deleteChecklist,
  deleteConversation,
  GUEST_NAMESPACE,
  InheritanceDb,
  listConversations,
  loadChecklist,
  loadMessages,
  type MessageRecord,
  type StorageNamespace,
} from "./db"

const ACCOUNT_A = accountNamespace("user-a")
const ACCOUNT_B = accountNamespace("user-b")

const checklist = (read: ProcedureId[] = []): ChecklistSnapshot => ({
  answers: {
    relationship: "descendant",
    deathDate: null,
    deathDateUnknown: true,
    oneStopApplication: "unknown",
  },
  riskAnswers: { debt: { riskId: "debt", answer: "unknown", confirmed: true } },
  procedureStates: Object.fromEntries(
    (["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"] as const).map((id) => [
      id,
      { guidanceRead: read.includes(id), needsRecheck: false },
    ]),
  ) as Record<ProcedureId, ProcedureState>,
})

const conversation = (
  id: string,
  namespace: StorageNamespace,
  updatedAt = 1,
): ConversationRecord => ({ id, namespace, title: `${id} 첫 질문`, createdAt: 1, updatedAt })

const message = (
  id: string,
  conversationId: string,
  namespace: StorageNamespace,
  createdAt: number,
): MessageRecord => ({
  id,
  conversationId,
  namespace,
  role: "user",
  content: `${id} 내용`,
  sources: [],
  createdAt,
})

let db: InheritanceDb

const putChecklist = (namespace: StorageNamespace, snapshot = checklist()) =>
  db.checklists.put({ ...snapshot, namespace, updatedAt: 1 })

const ids = async (namespace: StorageNamespace) => {
  const result = await listConversations(db, namespace)
  return result.ok ? result.value.map((c) => c.id) : result
}

beforeEach(() => {
  db = new InheritanceDb("test-db", { indexedDB: new IDBFactory(), IDBKeyRange })
})

afterEach(() => {
  db.close()
  vi.restoreAllMocks()
})

describe("accountNamespace", () => {
  it("계정 ID가 'guest'여도 비로그인 namespace와 겹치지 않는다", () => {
    expect(accountNamespace("guest")).not.toBe(GUEST_NAMESPACE)
  })

  it("빈 계정 ID는 거부한다", () => {
    expect(() => accountNamespace("  ")).toThrow()
  })
})

describe("체크리스트 읽기·삭제", () => {
  it("저장된 namespace에서만 복원되고 다른 계정에서는 보이지 않는다", async () => {
    await putChecklist(ACCOUNT_A, checklist(["p01"]))

    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: checklist(["p01"]) })
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: null })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("한 계정의 체크리스트 삭제는 다른 계정 기록을 지우지 않는다", async () => {
    await putChecklist(ACCOUNT_A)
    await putChecklist(ACCOUNT_B)

    await deleteChecklist(db, ACCOUNT_A)

    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: null })
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: checklist() })
  })
})

describe("AI 대화 읽기·삭제", () => {
  it("대화 목록은 해당 namespace 것만 최근에 이어 쓴 순서로 돌려준다", async () => {
    await db.conversations.bulkPut([
      conversation("c1", ACCOUNT_A, 10),
      conversation("c2", ACCOUNT_A, 30),
      conversation("c3", ACCOUNT_B, 20),
    ])

    expect(await ids(ACCOUNT_A)).toEqual(["c2", "c1"])
  })

  it("메시지는 작성 순서로 읽히고 다른 계정에서는 조회되지 않는다", async () => {
    await db.conversations.put(conversation("c1", ACCOUNT_A))
    await db.messages.bulkPut([
      message("m2", "c1", ACCOUNT_A, 50),
      message("m1", "c1", ACCOUNT_A, 40),
    ])

    const own = await loadMessages(db, ACCOUNT_A, "c1")

    expect(own.ok && own.value.map((m) => m.id)).toEqual(["m1", "m2"])
    expect(await loadMessages(db, ACCOUNT_B, "c1")).toEqual({ ok: true, value: [] })
  })

  it("다른 계정의 대화는 지울 수 없다", async () => {
    await db.conversations.put(conversation("c1", ACCOUNT_A))

    expect(await deleteConversation(db, ACCOUNT_B, "c1")).toEqual({
      ok: false,
      reason: "not-found",
    })
    expect(await ids(ACCOUNT_A)).toEqual(["c1"])
  })

  it("대화 하나를 지우면 그 대화의 메시지만 함께 지워진다", async () => {
    await db.conversations.bulkPut([
      conversation("c1", GUEST_NAMESPACE),
      conversation("c2", GUEST_NAMESPACE),
    ])
    await db.messages.bulkPut([
      message("m1", "c1", GUEST_NAMESPACE, 1),
      message("m2", "c2", GUEST_NAMESPACE, 2),
    ])

    expect(await deleteConversation(db, GUEST_NAMESPACE, "c1")).toEqual({
      ok: true,
      value: undefined,
    })
    expect(await ids(GUEST_NAMESPACE)).toEqual(["c2"])
    expect(await db.messages.count()).toBe(1)
  })
})

describe("삭제 범위 분리(D-04)", () => {
  it("[대화 기록 삭제]는 체크리스트와 다른 계정 대화를 지우지 않는다", async () => {
    await putChecklist(ACCOUNT_A)
    await db.conversations.bulkPut([conversation("a1", ACCOUNT_A), conversation("b1", ACCOUNT_B)])
    await db.messages.bulkPut([
      message("am1", "a1", ACCOUNT_A, 1),
      message("bm1", "b1", ACCOUNT_B, 1),
    ])

    await deleteAllConversations(db, ACCOUNT_A)

    expect(await ids(ACCOUNT_A)).toEqual([])
    expect(await loadMessages(db, ACCOUNT_A, "a1")).toEqual({ ok: true, value: [] })
    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: checklist() })
    expect(await ids(ACCOUNT_B)).toEqual(["b1"])
  })

  it("[체크리스트 삭제]는 대화 기록을 지우지 않는다", async () => {
    await putChecklist(GUEST_NAMESPACE)
    await db.conversations.put(conversation("c1", GUEST_NAMESPACE))

    await deleteChecklist(db, GUEST_NAMESPACE)

    expect(await ids(GUEST_NAMESPACE)).toEqual(["c1"])
  })
})

describe("실패 결과 변환(D-10, 4-2-4)", () => {
  it("IndexedDB를 쓸 수 없는 환경이면 성공 대신 unavailable을 돌려준다", async () => {
    // 전역 IndexedDB가 없는 Node 환경을 그대로 써서 사생활 보호 모드 등 미지원 상황을 흉내 낸다.
    const unsupported = new InheritanceDb("unsupported-db")

    expect(await loadChecklist(unsupported, GUEST_NAMESPACE)).toEqual({
      ok: false,
      reason: "unavailable",
    })
    expect(await deleteChecklist(unsupported, GUEST_NAMESPACE)).toEqual({
      ok: false,
      reason: "unavailable",
    })
  })

  it("Dexie가 감싼 용량 초과 오류도 quota-exceeded로 돌려준다", async () => {
    const wrapped = Object.assign(new Error("transaction aborted"), {
      name: "AbortError",
      inner: new DOMException("저장 공간 부족", "QuotaExceededError"),
    })
    vi.spyOn(db.checklists, "delete").mockRejectedValue(wrapped)

    expect(await deleteChecklist(db, GUEST_NAMESPACE)).toEqual({
      ok: false,
      reason: "quota-exceeded",
    })
  })

  it("알 수 없는 오류도 예외를 던지지 않고 unknown으로 돌려준다", async () => {
    vi.spyOn(db.conversations, "where").mockImplementation(() => {
      throw new Error("예상 못 한 오류")
    })

    expect(await listConversations(db, GUEST_NAMESPACE)).toEqual({ ok: false, reason: "unknown" })
  })
})
