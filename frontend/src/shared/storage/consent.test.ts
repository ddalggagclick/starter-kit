// 저장 동의 단위 테스트(4-1-2, 4-3-2~4-3-4의 로컬 저장 부분): 동의 2종 독립, 계정 경계, 트랜잭션 원자성,
// 삭제와 철회 구분, 실패 시 동의 유지. 화면 흐름(정책 확인·삭제 버튼·재시도)은 검증하지 않는다.
// fake-indexeddb로 실행한다. 실제 브라우저의 저장 차단·용량 초과는 검증하지 않는다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureState } from "@/shared/state/inheritance-store"
import {
  deleteScopeData,
  grantConsent,
  loadConsentStatuses,
  type NewConversation,
  type NewMessage,
  revokeConsent,
  saveChatWithConsent,
  saveChecklistWithConsent,
} from "./consent"
import {
  accountNamespace,
  type ChecklistSnapshot,
  GUEST_NAMESPACE,
  InheritanceDb,
  listConversations,
  loadChecklist,
  loadMessages,
  type StorageNamespace,
} from "./db"

const ACCOUNT_A = accountNamespace("user-a")
const ACCOUNT_B = accountNamespace("user-b")

const snapshot = (read: ProcedureId[] = ["p01"]): ChecklistSnapshot => ({
  answers: {
    relationship: "spouse",
    deathDate: "2026-09-30",
    deathDateUnknown: false,
    oneStopApplication: "yes",
  },
  riskAnswers: {},
  procedureStates: Object.fromEntries(
    (["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"] as const).map((id) => [
      id,
      { guidanceRead: read.includes(id), needsRecheck: false },
    ]),
  ) as Record<ProcedureId, ProcedureState>,
})

const conversation = (id: string, updatedAt = 1): NewConversation => ({
  id,
  title: `${id} 첫 질문`,
  createdAt: 1,
  updatedAt,
})

const message = (id: string, conversationId: string, createdAt: number): NewMessage => ({
  id,
  conversationId,
  role: "user",
  content: `${id} 내용`,
  sources: [],
  createdAt,
})

let db: InheritanceDb

beforeEach(() => {
  db = new InheritanceDb("consent-test-db", { indexedDB: new IDBFactory(), IDBKeyRange })
})

afterEach(() => {
  db.close()
  vi.restoreAllMocks()
})

const consentAll = async (namespace: StorageNamespace) => {
  await grantConsent(db, namespace, "checklist")
  await grantConsent(db, namespace, "chat")
}

// 동의를 거쳐 체크리스트와 대화 1건(메시지 1개)을 저장해 둔다.
const seed = async (namespace: StorageNamespace = GUEST_NAMESPACE) => {
  await consentAll(namespace)
  await saveChecklistWithConsent(db, namespace, snapshot())
  await saveChatWithConsent(db, namespace, {
    conversation: conversation("c1"),
    messages: [message("m1", "c1", 1)],
  })
}

const conversationIds = async (namespace: StorageNamespace = GUEST_NAMESPACE) => {
  const result = await listConversations(db, namespace)
  return result.ok ? result.value.map((c) => c.id) : result
}

const OK = { ok: true, value: undefined }

describe("동의 상태", () => {
  it("처음에는 두 항목 모두 미동의다", async () => {
    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "not-consented",
      chat: "not-consented",
    })
  })

  it("체크리스트만 동의하면 AI 대화는 미동의로 남는다(D-03)", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "checklist")

    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "ready",
      chat: "not-consented",
    })
  })

  it("한 계정의 동의는 Guest나 다른 계정에 적용되지 않는다", async () => {
    await consentAll(ACCOUNT_A)

    expect(await loadConsentStatuses(db, ACCOUNT_B)).toEqual({
      checklist: "not-consented",
      chat: "not-consented",
    })
    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "not-consented",
      chat: "not-consented",
    })
  })

  it("동의 기록을 읽지 못하면 두 항목 모두 failed다(D-10)", async () => {
    const unsupported = new InheritanceDb("unsupported-consent-db")

    expect(await loadConsentStatuses(unsupported, GUEST_NAMESPACE)).toEqual({
      checklist: "failed",
      chat: "failed",
    })
  })
})

describe("체크리스트 저장", () => {
  it("동의하지 않았으면 저장하지 않고 not-consented를 돌려준다", async () => {
    expect(await saveChecklistWithConsent(db, GUEST_NAMESPACE, snapshot())).toEqual({
      ok: false,
      reason: "not-consented",
    })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("AI 대화 동의만으로는 체크리스트를 저장할 수 없다", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "chat")

    expect(await saveChecklistWithConsent(db, GUEST_NAMESPACE, snapshot())).toEqual({
      ok: false,
      reason: "not-consented",
    })
  })

  it("동의하면 저장되고, 다시 저장하면 같은 기록을 최신 상태로 바꾼다", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "checklist")

    expect(await saveChecklistWithConsent(db, GUEST_NAMESPACE, snapshot(["p01"]))).toEqual(OK)
    expect(await saveChecklistWithConsent(db, GUEST_NAMESPACE, snapshot(["p01", "p05"]))).toEqual(
      OK,
    )

    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({
      ok: true,
      value: snapshot(["p01", "p05"]),
    })
    expect(await db.checklists.count()).toBe(1)
  })
})

describe("계정·동의 경계(리뷰 회귀)", () => {
  it("A만 동의한 상태에서 B로 저장하면 거부되고 B 데이터가 생기지 않는다", async () => {
    await consentAll(ACCOUNT_A)

    expect(await saveChecklistWithConsent(db, ACCOUNT_B, snapshot())).toEqual({
      ok: false,
      reason: "not-consented",
    })
    expect(
      await saveChatWithConsent(db, ACCOUNT_B, {
        conversation: conversation("c1"),
        messages: [message("m1", "c1", 1)],
      }),
    ).toEqual({ ok: false, reason: "not-consented" })

    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: null })
    expect(await conversationIds(ACCOUNT_B)).toEqual([])
    expect(await db.messages.count()).toBe(0)
  })

  it("입력에 다른 계정 namespace가 섞여 들어와도 동의를 확인한 계정으로 저장된다", async () => {
    await consentAll(ACCOUNT_A)
    // 타입을 우회해 namespace를 끼워 넣는 호출을 흉내 낸다.
    const smuggledConversation = { ...conversation("c1"), namespace: ACCOUNT_B } as NewConversation
    const smuggledMessage = { ...message("m1", "c1", 1), namespace: ACCOUNT_B } as NewMessage
    const smuggledChecklist = { ...snapshot(), namespace: ACCOUNT_B } as ChecklistSnapshot

    await saveChatWithConsent(db, ACCOUNT_A, {
      conversation: smuggledConversation,
      messages: [smuggledMessage],
    })
    await saveChecklistWithConsent(db, ACCOUNT_A, smuggledChecklist)

    expect(await conversationIds(ACCOUNT_A)).toEqual(["c1"])
    expect(await conversationIds(ACCOUNT_B)).toEqual([])
    expect(await loadMessages(db, ACCOUNT_B, "c1")).toEqual({ ok: true, value: [] })
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: null })
    expect((await loadChecklist(db, ACCOUNT_A)).ok).toBe(true)
  })

  it("다른 계정의 대화에는 메시지를 추가할 수 없다", async () => {
    await consentAll(ACCOUNT_A)
    await consentAll(ACCOUNT_B)
    await saveChatWithConsent(db, ACCOUNT_A, { conversation: conversation("c1") })

    expect(
      await saveChatWithConsent(db, ACCOUNT_B, { messages: [message("m1", "c1", 1)] }),
    ).toEqual({ ok: false, reason: "not-found" })
    expect(await db.messages.count()).toBe(0)
  })
})

describe("AI 대화 저장", () => {
  beforeEach(async () => {
    await consentAll(ACCOUNT_A)
    await consentAll(ACCOUNT_B)
    await consentAll(GUEST_NAMESPACE)
  })

  it("두 계정이 같은 대화 ID를 써도 각자의 대화로 따로 저장된다", async () => {
    await saveChatWithConsent(db, ACCOUNT_A, { conversation: conversation("c1") })
    await saveChatWithConsent(db, ACCOUNT_B, { conversation: conversation("c1") })

    expect(await conversationIds(ACCOUNT_A)).toEqual(["c1"])
    expect(await conversationIds(ACCOUNT_B)).toEqual(["c1"])
    expect(await db.conversations.count()).toBe(2)
  })

  it("두 계정이 같은 메시지 ID를 써도 서로의 메시지를 덮어쓰지 않는다", async () => {
    await saveChatWithConsent(db, ACCOUNT_A, {
      conversation: conversation("c1"),
      messages: [message("m1", "c1", 1)],
    })
    await saveChatWithConsent(db, ACCOUNT_B, {
      conversation: conversation("c1"),
      messages: [message("m1", "c1", 2)],
    })

    const a = await loadMessages(db, ACCOUNT_A, "c1")
    const b = await loadMessages(db, ACCOUNT_B, "c1")
    expect(a.ok && a.value.map((m) => m.createdAt)).toEqual([1])
    expect(b.ok && b.value.map((m) => m.createdAt)).toEqual([2])
  })

  it("두 계정이 같은 대화 ID로 동시에 저장해도 둘 다 남는다", async () => {
    const results = await Promise.all([
      saveChatWithConsent(db, ACCOUNT_A, { conversation: conversation("c1") }),
      saveChatWithConsent(db, ACCOUNT_B, { conversation: conversation("c1") }),
    ])

    expect(results).toEqual([OK, OK])
    expect(await db.conversations.count()).toBe(2)
  })

  it("메시지를 추가하면 대화가 목록 맨 위로 오고, 오래된 메시지가 늦게 와도 순서가 돌아가지 않는다", async () => {
    await saveChatWithConsent(db, GUEST_NAMESPACE, { conversation: conversation("c1", 10) })
    await saveChatWithConsent(db, GUEST_NAMESPACE, { conversation: conversation("c2", 20) })
    await saveChatWithConsent(db, GUEST_NAMESPACE, { messages: [message("m2", "c1", 50)] })
    await saveChatWithConsent(db, GUEST_NAMESPACE, { messages: [message("m1", "c1", 5)] })

    expect(await conversationIds()).toEqual(["c1", "c2"])
    expect((await db.conversations.get([GUEST_NAMESPACE, "c1"]))?.updatedAt).toBe(50)
    const messages = await loadMessages(db, GUEST_NAMESPACE, "c1")
    expect(messages.ok && messages.value.map((m) => m.id)).toEqual(["m1", "m2"])
  })
})

describe("트랜잭션 원자성(리뷰 회귀)", () => {
  beforeEach(() => consentAll(GUEST_NAMESPACE))

  it("대화를 먼저 저장한 뒤 메시지 대상 대화가 없으면 먼저 저장한 대화도 남지 않는다", async () => {
    const result = await saveChatWithConsent(db, GUEST_NAMESPACE, {
      conversation: conversation("c1"),
      messages: [message("m1", "missing", 1)],
    })

    expect(result).toEqual({ ok: false, reason: "not-found" })
    expect(await conversationIds()).toEqual([])
    expect(await db.messages.count()).toBe(0)
  })

  it("대화 저장 후 메시지 저장이 용량 초과로 실패하면 아무 데이터도 남지 않는다", async () => {
    vi.spyOn(db.messages, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )

    const result = await saveChatWithConsent(db, GUEST_NAMESPACE, {
      conversation: conversation("c1"),
      messages: [message("m1", "c1", 1)],
    })

    expect(result).toEqual({ ok: false, reason: "quota-exceeded" })
    vi.restoreAllMocks()
    expect(await conversationIds()).toEqual([])
    expect(await db.messages.count()).toBe(0)
  })

  it("여러 메시지 중 뒤의 것이 실패하면 앞 메시지와 updatedAt 갱신도 되돌린다", async () => {
    await saveChatWithConsent(db, GUEST_NAMESPACE, { conversation: conversation("c1", 10) })

    const result = await saveChatWithConsent(db, GUEST_NAMESPACE, {
      messages: [message("m1", "c1", 20), message("m2", "missing", 30)],
    })

    expect(result).toEqual({ ok: false, reason: "not-found" })
    expect(await db.messages.count()).toBe(0)
    expect((await db.conversations.get([GUEST_NAMESPACE, "c1"]))?.updatedAt).toBe(10)
  })
})

describe("데이터 삭제(4-3-2)", () => {
  it("[체크리스트 삭제]는 체크리스트만 지우고 동의와 대화 기록은 남긴다", async () => {
    await seed()

    expect(await deleteScopeData(db, GUEST_NAMESPACE, "checklist")).toEqual(OK)

    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
    expect(await conversationIds()).toEqual(["c1"])
    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "ready",
      chat: "ready",
    })
  })

  it("[대화 기록 삭제]는 대화만 지우고 동의와 체크리스트는 남긴다", async () => {
    await seed()

    await deleteScopeData(db, GUEST_NAMESPACE, "chat")

    expect(await conversationIds()).toEqual([])
    expect(await db.messages.count()).toBe(0)
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot() })
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).chat).toBe("ready")
  })
})

describe("동의 철회(4-3-3)", () => {
  it("대화 동의를 철회하면 대화 기록과 대화 동의만 사라진다", async () => {
    await seed()

    expect(await revokeConsent(db, GUEST_NAMESPACE, "chat")).toEqual(OK)

    expect(await conversationIds()).toEqual([])
    expect(await db.messages.count()).toBe(0)
    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "ready",
      chat: "not-consented",
    })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot() })
  })

  it("철회 뒤에는 다시 동의하기 전까지 저장할 수 없다", async () => {
    await seed()
    await revokeConsent(db, GUEST_NAMESPACE, "checklist")

    expect(await saveChecklistWithConsent(db, GUEST_NAMESPACE, snapshot())).toEqual({
      ok: false,
      reason: "not-consented",
    })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("한 계정의 철회는 다른 계정의 동의와 데이터에 영향이 없다", async () => {
    await seed(ACCOUNT_A)
    await seed(ACCOUNT_B)

    await revokeConsent(db, ACCOUNT_A, "chat")
    await revokeConsent(db, ACCOUNT_A, "checklist")

    expect(await conversationIds(ACCOUNT_B)).toEqual(["c1"])
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: snapshot() })
    expect(await loadConsentStatuses(db, ACCOUNT_B)).toEqual({ checklist: "ready", chat: "ready" })
  })
})

describe("삭제·철회 실패(4-3-4 로컬 부분)", () => {
  it("철회 중 데이터 삭제가 실패하면 완료로 돌려주지 않고 데이터와 동의가 모두 남는다", async () => {
    await seed()
    vi.spyOn(db.checklists, "delete").mockRejectedValue(new Error("삭제 실패"))

    const result = await revokeConsent(db, GUEST_NAMESPACE, "checklist")

    expect(result.ok).toBe(false)
    vi.restoreAllMocks()
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot() })
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).checklist).toBe("ready")
  })

  it("데이터를 지운 뒤 동의 해제가 실패하면 지운 데이터도 되돌린다", async () => {
    await seed()
    vi.spyOn(db.consents, "delete").mockRejectedValue(new Error("동의 해제 실패"))

    const result = await revokeConsent(db, GUEST_NAMESPACE, "chat")

    expect(result.ok).toBe(false)
    vi.restoreAllMocks()
    expect(await conversationIds()).toEqual(["c1"])
    expect(await db.messages.count()).toBe(1)
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).chat).toBe("ready")
  })

  it("일반 삭제가 실패하면 완료로 돌려주지 않는다", async () => {
    await seed()
    vi.spyOn(db.checklists, "delete").mockRejectedValue(
      new DOMException("차단됨", "InvalidStateError"),
    )

    expect(await deleteScopeData(db, GUEST_NAMESPACE, "checklist")).toEqual({
      ok: false,
      reason: "unavailable",
    })
  })
})
