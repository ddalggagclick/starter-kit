// 저장 동의 단위 테스트(4-1-2, 4-3-2~4-3-4): 동의 2종 독립, 삭제와 철회 구분, namespace 격리, 실패 시 동의 유지.
// fake-indexeddb로 실행한다. 실제 브라우저의 저장 차단·용량 초과는 검증하지 않는다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureState } from "@/shared/state/inheritance-store"
import {
  deleteScopeData,
  grantConsent,
  loadConsentStatuses,
  revokeConsent,
  writeWithConsent,
} from "./consent"
import {
  accountNamespace,
  addMessage,
  type ChecklistSnapshot,
  GUEST_NAMESPACE,
  InheritanceDb,
  listConversations,
  loadChecklist,
  saveChecklist,
  saveConversation,
} from "./db"

const ACCOUNT_A = accountNamespace("user-a")
const ACCOUNT_B = accountNamespace("user-b")

const snapshot: ChecklistSnapshot = {
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
      { guidanceRead: id === "p01", needsRecheck: false },
    ]),
  ) as Record<ProcedureId, ProcedureState>,
}

let db: InheritanceDb

beforeEach(() => {
  db = new InheritanceDb("consent-test-db", { indexedDB: new IDBFactory(), IDBKeyRange })
})

afterEach(() => {
  db.close()
  vi.restoreAllMocks()
})

// 동의를 거쳐 체크리스트와 대화 1건씩을 저장해 둔다.
const seed = async (namespace = GUEST_NAMESPACE) => {
  await grantConsent(db, namespace, "checklist")
  await grantConsent(db, namespace, "chat")
  await writeWithConsent(db, namespace, "checklist", () => saveChecklist(db, namespace, snapshot))
  await writeWithConsent(db, namespace, "chat", async () => {
    const saved = await saveConversation(db, {
      id: "c1",
      namespace,
      title: "상속포기 기한이 …",
      createdAt: 1,
      updatedAt: 1,
    })
    if (!saved.ok) return saved
    return addMessage(db, {
      id: "m1",
      conversationId: "c1",
      namespace,
      role: "user",
      content: "상속포기 기한이 언제부터인가요?",
      sources: [],
      createdAt: 1,
    })
  })
}

const conversationIds = async (namespace = GUEST_NAMESPACE) => {
  const result = await listConversations(db, namespace)
  return result.ok ? result.value.map((c) => c.id) : result
}

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
    await grantConsent(db, ACCOUNT_A, "checklist")
    await grantConsent(db, ACCOUNT_A, "chat")

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

describe("동의 확인 후 저장(4-1-2)", () => {
  it("동의하지 않은 항목은 저장 함수를 실행하지 않고 not-consented를 돌려준다", async () => {
    const write = vi.fn(() => saveChecklist(db, GUEST_NAMESPACE, snapshot))

    expect(await writeWithConsent(db, GUEST_NAMESPACE, "checklist", write)).toEqual({
      ok: false,
      reason: "not-consented",
    })
    expect(write).not.toHaveBeenCalled()
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("체크리스트 동의만으로는 AI 대화를 저장할 수 없다", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "checklist")

    const result = await writeWithConsent(db, GUEST_NAMESPACE, "chat", () =>
      saveConversation(db, {
        id: "c1",
        namespace: GUEST_NAMESPACE,
        title: "질문",
        createdAt: 1,
        updatedAt: 1,
      }),
    )

    expect(result).toEqual({ ok: false, reason: "not-consented" })
    expect(await conversationIds()).toEqual([])
  })

  it("동의한 항목은 저장 함수의 결과를 그대로 돌려준다", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "checklist")

    expect(
      await writeWithConsent(db, GUEST_NAMESPACE, "checklist", () =>
        saveChecklist(db, GUEST_NAMESPACE, snapshot),
      ),
    ).toEqual({ ok: true, value: undefined })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot })
  })

  it("저장 함수가 실패하면 성공으로 바꾸지 않는다", async () => {
    await grantConsent(db, GUEST_NAMESPACE, "checklist")

    const result = await writeWithConsent(db, GUEST_NAMESPACE, "checklist", async () => ({
      ok: false,
      reason: "quota-exceeded",
    }))

    expect(result).toEqual({ ok: false, reason: "quota-exceeded" })
  })
})

describe("데이터 삭제(4-3-2)", () => {
  it("[체크리스트 삭제]는 체크리스트만 지우고 동의와 대화 기록은 남긴다", async () => {
    await seed()

    expect(await deleteScopeData(db, GUEST_NAMESPACE, "checklist")).toEqual({
      ok: true,
      value: undefined,
    })

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
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot })
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).chat).toBe("ready")
  })
})

describe("동의 철회(4-3-3)", () => {
  it("대화 동의를 철회하면 대화 기록과 대화 동의만 사라진다", async () => {
    await seed()

    expect(await revokeConsent(db, GUEST_NAMESPACE, "chat")).toEqual({
      ok: true,
      value: undefined,
    })

    expect(await conversationIds()).toEqual([])
    expect(await db.messages.count()).toBe(0)
    expect(await loadConsentStatuses(db, GUEST_NAMESPACE)).toEqual({
      checklist: "ready",
      chat: "not-consented",
    })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot })
  })

  it("철회 뒤에는 다시 동의하기 전까지 저장할 수 없다", async () => {
    await seed()
    await revokeConsent(db, GUEST_NAMESPACE, "checklist")

    const result = await writeWithConsent(db, GUEST_NAMESPACE, "checklist", () =>
      saveChecklist(db, GUEST_NAMESPACE, snapshot),
    )

    expect(result).toEqual({ ok: false, reason: "not-consented" })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("한 계정의 철회는 다른 계정의 동의와 데이터에 영향이 없다", async () => {
    await seed(ACCOUNT_A)
    await seed(ACCOUNT_B)

    await revokeConsent(db, ACCOUNT_A, "chat")
    await revokeConsent(db, ACCOUNT_A, "checklist")

    expect(await conversationIds(ACCOUNT_B)).toEqual(["c1"])
    expect(await loadChecklist(db, ACCOUNT_B)).toEqual({ ok: true, value: snapshot })
    expect(await loadConsentStatuses(db, ACCOUNT_B)).toEqual({ checklist: "ready", chat: "ready" })
  })
})

describe("삭제·철회 실패(4-3-4)", () => {
  it("철회 중 데이터 삭제가 실패하면 완료로 돌려주지 않고 데이터와 동의가 모두 남는다", async () => {
    await seed()
    vi.spyOn(db.checklists, "delete").mockRejectedValue(new Error("삭제 실패"))

    const result = await revokeConsent(db, GUEST_NAMESPACE, "checklist")

    expect(result.ok).toBe(false)
    vi.restoreAllMocks()
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: snapshot })
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
