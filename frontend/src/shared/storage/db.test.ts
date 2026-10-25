// Dexie 저장소 단위 테스트(4-2-1, 4-2-2, 4-2-4): namespace 격리, 체크리스트·대화 삭제 분리, 저장 실패 결과.
// fake-indexeddb는 Node에서 IndexedDB 규격을 메모리로 흉내 낸다. 실제 브라우저 차단·용량 동작은 검증하지 않는다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureState } from "@/shared/state/inheritance-store"
import {
  accountNamespace,
  addMessage,
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
  saveChecklist,
  saveConversation,
} from "./db"

const ACCOUNT_A = accountNamespace("user-a")
const ACCOUNT_B = accountNamespace("user-b")

const procedureStates = (read: ProcedureId[] = []) =>
  Object.fromEntries(
    (["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"] as const).map((id) => [
      id,
      { guidanceRead: read.includes(id), needsRecheck: false },
    ]),
  ) as Record<ProcedureId, ProcedureState>

const checklist = (read: ProcedureId[] = []): ChecklistSnapshot => ({
  answers: {
    relationship: "descendant",
    deathDate: null,
    deathDateUnknown: true,
    oneStopApplication: "unknown",
  },
  riskAnswers: { debt: { riskId: "debt", answer: "unknown", confirmed: true } },
  procedureStates: procedureStates(read),
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

describe("체크리스트 저장", () => {
  it("저장한 namespace에서만 복원되고 다른 계정에서는 보이지 않는다", async () => {
    expect(await saveChecklist(db, ACCOUNT_A, checklist(["p01"]))).toEqual({
      ok: true,
      value: undefined,
    })

    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: checklist(["p01"]) })
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: null })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("다시 저장하면 같은 namespace 기록을 최신 상태로 바꾼다", async () => {
    await saveChecklist(db, GUEST_NAMESPACE, checklist(["p01"]))
    await saveChecklist(db, GUEST_NAMESPACE, checklist(["p01", "p05"]))

    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({
      ok: true,
      value: checklist(["p01", "p05"]),
    })
    expect(await db.checklists.count()).toBe(1)
  })

  it("한 계정의 체크리스트 삭제는 다른 계정 기록을 지우지 않는다", async () => {
    await saveChecklist(db, ACCOUNT_A, checklist())
    await saveChecklist(db, ACCOUNT_B, checklist())

    await deleteChecklist(db, ACCOUNT_A)

    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: null })
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: checklist() })
  })
})

describe("AI 대화 저장", () => {
  it("대화 목록은 해당 namespace 것만 최근에 이어 쓴 순서로 돌려준다", async () => {
    await saveConversation(db, conversation("c1", ACCOUNT_A, 10))
    await saveConversation(db, conversation("c2", ACCOUNT_A, 30))
    await saveConversation(db, conversation("c3", ACCOUNT_B, 20))

    const result = await listConversations(db, ACCOUNT_A)

    expect(result.ok && result.value.map((c) => c.id)).toEqual(["c2", "c1"])
  })

  it("메시지를 추가하면 대화가 목록 맨 위로 오고, 메시지는 작성 순서로 읽힌다", async () => {
    await saveConversation(db, conversation("c1", GUEST_NAMESPACE, 10))
    await saveConversation(db, conversation("c2", GUEST_NAMESPACE, 20))
    await addMessage(db, message("m2", "c1", GUEST_NAMESPACE, 50))
    await addMessage(db, message("m1", "c1", GUEST_NAMESPACE, 40))

    const list = await listConversations(db, GUEST_NAMESPACE)
    const messages = await loadMessages(db, GUEST_NAMESPACE, "c1")

    expect(list.ok && list.value.map((c) => c.id)).toEqual(["c1", "c2"])
    expect(messages.ok && messages.value.map((m) => m.id)).toEqual(["m1", "m2"])
  })

  it("다른 계정의 대화에는 메시지를 추가·조회·삭제할 수 없다", async () => {
    await saveConversation(db, conversation("c1", ACCOUNT_A))
    await addMessage(db, message("m1", "c1", ACCOUNT_A, 5))

    expect(await addMessage(db, message("m2", "c1", ACCOUNT_B, 6))).toEqual({
      ok: false,
      reason: "not-found",
    })
    expect(await loadMessages(db, ACCOUNT_B, "c1")).toEqual({ ok: true, value: [] })
    expect(await deleteConversation(db, ACCOUNT_B, "c1")).toEqual({
      ok: false,
      reason: "not-found",
    })

    const messages = await loadMessages(db, ACCOUNT_A, "c1")
    expect(messages.ok && messages.value.map((m) => m.id)).toEqual(["m1"])
  })

  it("같은 대화 ID로 다른 계정의 대화를 덮어쓰지 않는다", async () => {
    await saveConversation(db, conversation("c1", ACCOUNT_A))

    expect(await saveConversation(db, conversation("c1", ACCOUNT_B))).toEqual({
      ok: false,
      reason: "not-found",
    })
    expect((await db.conversations.get("c1"))?.namespace).toBe(ACCOUNT_A)
  })

  it("대화 하나를 지우면 그 대화의 메시지만 함께 지워진다", async () => {
    await saveConversation(db, conversation("c1", GUEST_NAMESPACE))
    await saveConversation(db, conversation("c2", GUEST_NAMESPACE))
    await addMessage(db, message("m1", "c1", GUEST_NAMESPACE, 1))
    await addMessage(db, message("m2", "c2", GUEST_NAMESPACE, 2))

    expect(await deleteConversation(db, GUEST_NAMESPACE, "c1")).toEqual({
      ok: true,
      value: undefined,
    })

    const list = await listConversations(db, GUEST_NAMESPACE)
    expect(list.ok && list.value.map((c) => c.id)).toEqual(["c2"])
    expect(await db.messages.count()).toBe(1)
  })
})

describe("삭제 범위 분리(D-04)", () => {
  it("[대화 기록 삭제]는 체크리스트와 다른 계정 대화를 지우지 않는다", async () => {
    await saveChecklist(db, ACCOUNT_A, checklist())
    await saveConversation(db, conversation("a1", ACCOUNT_A))
    await addMessage(db, message("am1", "a1", ACCOUNT_A, 1))
    await saveConversation(db, conversation("b1", ACCOUNT_B))
    await addMessage(db, message("bm1", "b1", ACCOUNT_B, 1))

    await deleteAllConversations(db, ACCOUNT_A)

    expect(await listConversations(db, ACCOUNT_A)).toEqual({ ok: true, value: [] })
    expect(await loadMessages(db, ACCOUNT_A, "a1")).toEqual({ ok: true, value: [] })
    expect(await loadChecklist(db, ACCOUNT_A)).toEqual({ ok: true, value: checklist() })
    const other = await listConversations(db, ACCOUNT_B)
    expect(other.ok && other.value.map((c) => c.id)).toEqual(["b1"])
  })

  it("[체크리스트 삭제]는 대화 기록을 지우지 않는다", async () => {
    await saveChecklist(db, GUEST_NAMESPACE, checklist())
    await saveConversation(db, conversation("c1", GUEST_NAMESPACE))

    await deleteChecklist(db, GUEST_NAMESPACE)

    const list = await listConversations(db, GUEST_NAMESPACE)
    expect(list.ok && list.value.map((c) => c.id)).toEqual(["c1"])
  })
})

describe("저장 실패(D-10, 4-2-4)", () => {
  it("IndexedDB를 쓸 수 없는 환경이면 성공 대신 unavailable을 돌려준다", async () => {
    // 전역 IndexedDB가 없는 Node 환경을 그대로 써서 사생활 보호 모드 등 미지원 상황을 흉내 낸다.
    const unsupported = new InheritanceDb("unsupported-db")

    expect(await saveChecklist(unsupported, GUEST_NAMESPACE, checklist())).toEqual({
      ok: false,
      reason: "unavailable",
    })
    expect(await loadChecklist(unsupported, GUEST_NAMESPACE)).toEqual({
      ok: false,
      reason: "unavailable",
    })
  })

  it("용량 초과 오류는 quota-exceeded로 돌려준다", async () => {
    vi.spyOn(db.checklists, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )

    expect(await saveChecklist(db, GUEST_NAMESPACE, checklist())).toEqual({
      ok: false,
      reason: "quota-exceeded",
    })
  })

  it("Dexie가 감싼 용량 초과 오류도 quota-exceeded로 돌려준다", async () => {
    const wrapped = Object.assign(new Error("transaction aborted"), {
      name: "AbortError",
      inner: new DOMException("저장 공간 부족", "QuotaExceededError"),
    })
    vi.spyOn(db.checklists, "put").mockRejectedValue(wrapped)

    expect(await saveChecklist(db, GUEST_NAMESPACE, checklist())).toEqual({
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
