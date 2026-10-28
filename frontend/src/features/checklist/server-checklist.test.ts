// 서버 체크리스트 저장(A17) 테스트(4-5-1, 4-6-1, 4-5-3, 4-6-3, 4-3-4 서버, 검증 ②). 요청을 세는 가짜 A17로 실행한다.
// A17은 계약 미확정·Backend 미구현이라 실제 서버 연동 검증이 아니다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import {
  accountNamespace,
  type ChecklistSnapshot,
  GUEST_NAMESPACE,
  InheritanceDb,
  loadChecklist,
} from "@/shared/storage/db"
import {
  grantChecklistStorage,
  revokeChecklistStorage,
  startChecklistPersistence,
} from "./checklist-storage"
import {
  grantServerSave,
  keepLocalOverServer,
  loadServerRecord,
  retryServerSave,
  revokeServerSave,
  type ServerChecklistSync,
  startServerChecklistSync,
  useServerChecklistStore,
} from "./server-checklist"
import type { ServerChecklistApi } from "./server-checklist-api"

const SPOUSE: InitialAnswers = {
  relationship: "spouse",
  deathDate: null,
  deathDateUnknown: true,
  oneStopApplication: "no",
}

// 서버 상태를 들고 있고 실패를 주입할 수 있는 가짜 A17
const fakeApi = (initial: { consent: boolean; snapshot: ChecklistSnapshot | null }) => {
  const server = { ...initial }
  const fail = { save: false, remove: false, read: false }
  const api: ServerChecklistApi & { calls: { read: number; save: number; remove: number } } = {
    calls: { read: 0, save: 0, remove: 0 },
    read: vi.fn(async () => {
      api.calls.read += 1
      if (fail.read) throw new Error("read")
      return { consent: server.consent, snapshot: server.consent ? server.snapshot : null }
    }),
    save: vi.fn(async (snapshot) => {
      api.calls.save += 1
      if (fail.save) throw new Error("save")
      server.consent = true
      server.snapshot = snapshot
    }),
    remove: vi.fn(async () => {
      api.calls.remove += 1
      if (fail.remove) throw new Error("remove")
      server.consent = false
      server.snapshot = null
    }),
  }
  return { api, server, fail }
}

const memory = () => useInheritanceStore.getState()
const server = () => useServerChecklistStore.getState()
let sync: ServerChecklistSync

beforeEach(() => memory().reset())
afterEach(() => sync?.stop())

const startAs = async (accountId: string | null, api: ServerChecklistApi | null) => {
  sync = startServerChecklistSync(accountId, api)
  await sync.ready
}

describe("요청 차단 (4-6-1)", () => {
  it("비로그인이면 서버 요청을 하나도 보내지 않는다", async () => {
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs(null, api)

    memory().setInitialAnswers(SPOUSE, "direct")
    await sync.flush()

    expect(api.calls).toEqual({ read: 0, save: 0, remove: 0 })
    expect(server().consent).toBe("off")
  })

  it("로그인했지만 서버 저장 동의 전이면 동의 상태 조회만 하고 체크리스트를 보내지 않는다", async () => {
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)

    memory().setInitialAnswers(SPOUSE, "direct")
    memory().setGuidanceRead("p01", true)
    await sync.flush()

    expect(server().consent).toBe("none")
    expect(api.calls).toEqual({ read: 1, save: 0, remove: 0 })
  })
})

describe("이 기기 저장 동의와 서버 저장 분리 (4-5-1, 4-6-1)", () => {
  // 4-5-1: 로컬(이 기기) 동의만으로는 서버(DB)에 올리지 않는다. 서버 저장은 별도 서버 동의가 있어야 한다.
  const startLocal = async (name: string, namespace: ReturnType<typeof accountNamespace>) => {
    const db = new InheritanceDb(name, { indexedDB: new IDBFactory(), IDBKeyRange })
    const local = startChecklistPersistence(db, namespace)
    await local.ready
    return { db, local }
  }

  it("로그인 + 이 기기 저장 동의만 있으면 이 기기에는 저장하고 서버에는 하나도 보내지 않는다", async () => {
    const { db, local } = await startLocal("local-only-member", accountNamespace("user-a"))
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")

    await grantChecklistStorage(db)
    memory().setGuidanceRead("p01", true)
    await sync.flush()

    await vi.waitFor(async () => {
      const saved = await loadChecklist(db, accountNamespace("user-a"))
      expect(saved.ok && saved.value?.procedureStates.p01.guidanceRead).toBe(true)
    })
    expect(api.calls.save).toBe(0)
    expect(server().consent).toBe("none")
    local.stop()
    db.close()
  })

  it("비로그인 + 이 기기 저장 동의가 있어도 서버 요청은 0건이다", async () => {
    const { db, local } = await startLocal("local-only-guest", GUEST_NAMESPACE)
    const { api } = fakeApi({ consent: true, snapshot: null })
    await startAs(null, api)
    memory().setInitialAnswers(SPOUSE, "direct")

    await grantChecklistStorage(db)
    memory().setGuidanceRead("p02", true)
    await sync.flush()

    await vi.waitFor(async () => {
      const saved = await loadChecklist(db, GUEST_NAMESPACE)
      expect(saved.ok && saved.value?.procedureStates.p02.guidanceRead).toBe(true)
    })
    expect(api.calls).toEqual({ read: 0, save: 0, remove: 0 })
    local.stop()
    db.close()
  })
})

describe("서버 저장 (4-5-3, T13-A)", () => {
  it("동의하면 지금 체크리스트를 저장하고, 이후 변경도 저장한다", async () => {
    const { api, server: stored } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")

    expect(await grantServerSave("user-a")).toBe(true)
    memory().setGuidanceRead("p03", true)
    await sync.flush()

    expect(server().consent).toBe("granted")
    expect(server().saveStatus).toBe("saved")
    expect(stored.snapshot?.procedureStates.p03.guidanceRead).toBe(true)
  })

  it("저장이 실패하면 서버 상태만 실패로 두고 화면은 그대로이며, 다시 시도로 저장한다", async () => {
    const { api, fail, server: stored } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    await grantServerSave("user-a")

    fail.save = true
    memory().setGuidanceRead("p02", true)
    await sync.flush()
    expect(server().saveStatus).toBe("failed")
    expect(memory().procedureStates.p02.guidanceRead).toBe(true)

    fail.save = false
    await retryServerSave("user-a")
    expect(server().saveStatus).toBe("saved")
    expect(stored.snapshot?.procedureStates.p02.guidanceRead).toBe(true)
  })

  it("동의 저장이 실패하면 동의되지 않은 것으로 남는다", async () => {
    const { api, fail } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    fail.save = true

    expect(await grantServerSave("user-a")).toBe(false)
    expect(server().consent).toBe("none")
    expect(server().saveStatus).toBe("failed")
  })
})

describe("자동 병합 금지 (4-6-3, S06-B)", () => {
  const SERVER_RECORD: ChecklistSnapshot = {
    answers: { ...SPOUSE, relationship: "sibling" },
    riskAnswers: { debt: { riskId: "debt", answer: "yes", confirmed: true } },
    procedureStates: {} as ChecklistSnapshot["procedureStates"],
  }

  it("서버 기록이 있으면 화면을 바꾸지 않고, 고르기 전에는 서버에 저장하지 않는다", async () => {
    memory().setInitialAnswers(SPOUSE, "direct")
    const { api } = fakeApi({ consent: true, snapshot: SERVER_RECORD })
    await startAs("user-a", api)

    expect(server().pending?.answers?.relationship).toBe("sibling")
    expect(memory().answers?.relationship).toBe("spouse")
    memory().setGuidanceRead("p01", true)
    await sync.flush()
    expect(api.calls.save).toBe(0)
  })

  it("[서버 기록 불러오기]를 고르면 화면을 서버 기록으로 바꾸고(위험 답변은 미확인) 이후 변경을 저장한다", async () => {
    memory().setInitialAnswers(SPOUSE, "direct")
    const { api } = fakeApi({ consent: true, snapshot: SERVER_RECORD })
    await startAs("user-a", api)

    loadServerRecord("user-a")

    expect(memory().answers?.relationship).toBe("sibling")
    expect(memory().riskAnswers.debt?.confirmed).toBe(false)
    memory().setGuidanceRead("p01", true)
    await sync.flush()
    expect(api.calls.save).toBe(1)
  })

  it("[이 기기 내용으로 서버 덮어쓰기]를 고르면 화면 내용을 서버에 저장한다", async () => {
    memory().setInitialAnswers(SPOUSE, "direct")
    const { api, server: stored } = fakeApi({ consent: true, snapshot: SERVER_RECORD })
    await startAs("user-a", api)

    await keepLocalOverServer("user-a")

    expect(stored.snapshot?.answers?.relationship).toBe("spouse")
    expect(server().pending).toBeNull()
  })
})

describe("서버 저장 철회 (4-3-4 서버)", () => {
  it("철회하면 서버 기록·동의를 지우고 이후 변경은 보내지 않는다", async () => {
    const { api, server: stored } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    await grantServerSave("user-a")

    expect(await revokeServerSave("user-a")).toBe(true)
    memory().setGuidanceRead("p05", true)
    await sync.flush()

    expect(server().consent).toBe("none")
    expect(server().revokeResult).toEqual({ ok: true })
    expect(stored.snapshot).toBeNull()
    expect(api.calls.save).toBe(1)
  })

  it("철회가 실패하면 서버 기록이 남았다고 표시하고, 서버만 다시 시도할 수 있다", async () => {
    const { api, fail } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    await grantServerSave("user-a")

    fail.remove = true
    expect(await revokeServerSave("user-a")).toBe(false)
    expect(server().revokeResult).toEqual({ ok: false })
    expect(server().consent).toBe("granted")

    fail.remove = false
    expect(await revokeServerSave("user-a")).toBe(true)
    expect(server().revokeResult).toEqual({ ok: true })
  })
})

describe("계정 고정", () => {
  it("A 계정으로 요청한 저장·철회는 지금 B 계정에 실행되지 않는다", async () => {
    const a = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", a.api)
    sync.stop()
    const b = fakeApi({ consent: true, snapshot: null })
    await startAs("user-b", b.api)

    expect(await grantServerSave("user-a")).toBe(false)
    expect(await revokeServerSave("user-a")).toBe(false)
    expect(b.api.calls.save + b.api.calls.remove).toBe(0)
    expect(a.api.calls.save + a.api.calls.remove).toBe(0)
  })
})

describe("이 기기·서버 삭제 분리 (리뷰 회귀)", () => {
  it("이 기기 기록 삭제로 화면이 비워져도 서버 기록을 빈 값으로 덮어쓰지 않는다", async () => {
    const { api, server: stored } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    await grantServerSave("user-a")

    memory().reset()
    await sync.flush()

    expect(api.calls.save).toBe(1)
    expect(stored.snapshot?.answers).toEqual(SPOUSE)
  })
})

describe("답이 없을 때 (리뷰 회귀: 빈 기록 전송)", () => {
  it("질문에 답하기 전에 [서버에 저장]을 눌러도 서버에 보내지 않고 동의도 기록하지 않는다", async () => {
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)

    expect(await grantServerSave("user-a")).toBe(false)

    expect(api.calls.save).toBe(0)
    expect(server().consent).toBe("none")
    expect(server().saveStatus).toBe("idle")
  })

  it("이 기기에 답이 없으면 [이 기기 내용으로 서버 덮어쓰기]를 해도 서버 기록과 선택 대기가 그대로다", async () => {
    const record: ChecklistSnapshot = {
      answers: SPOUSE,
      riskAnswers: {},
      procedureStates: {} as ChecklistSnapshot["procedureStates"],
    }
    const { api, server: stored } = fakeApi({ consent: true, snapshot: record })
    await startAs("user-a", api)

    await keepLocalOverServer("user-a")

    expect(api.calls.save).toBe(0)
    expect(stored.snapshot).toEqual(record)
    expect(server().pending).toEqual(record)
  })
})

describe("검증 ②: 이 기기 철회 성공 + 서버 철회 실패", () => {
  it("이 기기 기록은 지워지고, 서버에는 기록이 남았다고 표시되며 서버만 다시 시도한다", async () => {
    const db = new InheritanceDb("server-verify-2", { indexedDB: new IDBFactory(), IDBKeyRange })
    const namespace = accountNamespace("user-a")
    const local = startChecklistPersistence(db, namespace)
    await local.ready
    const { api, fail, server: stored } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    memory().setInitialAnswers(SPOUSE, "direct")
    await grantChecklistStorage(db)
    await grantServerSave("user-a")

    // 이 기기 철회 성공
    expect(await revokeChecklistStorage(namespace)).toBe(true)
    expect(await loadChecklist(db, namespace)).toEqual({ ok: true, value: null })
    // 서버 철회 실패 → 서버에 기록 남음
    fail.remove = true
    expect(await revokeServerSave("user-a")).toBe(false)
    expect(server().revokeResult).toEqual({ ok: false })
    expect(stored.snapshot?.answers).toEqual(SPOUSE)
    // 서버만 다시 시도
    fail.remove = false
    expect(await revokeServerSave("user-a")).toBe(true)
    expect(stored.snapshot).toBeNull()

    local.stop()
    db.close()
  })
})
