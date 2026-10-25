// 체크리스트 저장·복원 연결 테스트(4-2-1, 2-5-3, 4-1-2, 4-2-3, 4-2-4, 2-4-4).
// fake-indexeddb로 실행하고, "새로고침"은 메모리 스토어를 비운 뒤 같은 DB로 다시 시작해 흉내 낸다.
// 실제 브라우저의 저장 차단·용량 초과는 검증하지 않는다.
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { GUEST_NAMESPACE, InheritanceDb, loadChecklist } from "@/shared/storage/db"
import {
  type ChecklistPersistence,
  declineChecklistStorage,
  grantChecklistStorage,
  startChecklistPersistence,
  useChecklistStorageStore,
} from "./checklist-storage"

const ANSWERS: InitialAnswers = {
  relationship: "descendant",
  deathDate: "2026-09-30",
  deathDateUnknown: false,
  oneStopApplication: "yes",
}

const store = () => useInheritanceStore.getState()
const status = () => useChecklistStorageStore.getState().status

let db: InheritanceDb
let persistence: ChecklistPersistence

const start = async () => {
  persistence = startChecklistPersistence(db, GUEST_NAMESPACE)
  await persistence.ready
}

// 새로고침: 메모리는 사라지고 IndexedDB만 남는다.
const reload = async () => {
  await persistence.flush()
  persistence.stop()
  store().reset()
  await start()
}

beforeEach(() => {
  db = new InheritanceDb("checklist-storage-test", { indexedDB: new IDBFactory(), IDBKeyRange })
  store().reset()
})

afterEach(() => {
  persistence?.stop()
  db.close()
  vi.restoreAllMocks()
})

describe("동의 전", () => {
  it("미동의 상태로 시작하고, 체크리스트를 바꿔도 IndexedDB에 기록하지 않는다", async () => {
    await start()
    expect(status()).toBe("not-consented")

    store().setInitialAnswers(ANSWERS, "direct")
    store().setGuidanceRead("p01", true)
    await persistence.flush()

    expect(await db.checklists.count()).toBe(0)
  })

  it("[저장 안 함]은 저장하지 않고 다음 방문에 다시 묻는다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    declineChecklistStorage()

    await reload()

    expect(await db.checklists.count()).toBe(0)
    expect(status()).toBe("not-consented")
    expect(useChecklistStorageStore.getState().declined).toBe(false)
    expect(store().answers).toBeNull()
  })
})

describe("동의 후 저장·복원", () => {
  it("동의하는 순간 현재 메모리 상태를 저장하고 '저장 중'이 된다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    store().setGuidanceRead("p01", true)

    await grantChecklistStorage(db)

    expect(status()).toBe("ready")
    const saved = await loadChecklist(db, GUEST_NAMESPACE)
    expect(saved.ok && saved.value?.answers).toEqual(ANSWERS)
    expect(saved.ok && saved.value?.procedureStates.p01.guidanceRead).toBe(true)
  })

  it("동의 후 바뀐 안내 확인·재확인 배지도 저장되어 새로고침 뒤 복원된다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    await grantChecklistStorage(db)
    store().setGuidanceRead("p05", true)
    // 사망일 수정 → 이미 확인한 p05는 재확인 필요(2-4-3)
    store().setInitialAnswers({ ...ANSWERS, deathDate: "2026-10-01" }, "direct")

    await reload()

    expect(status()).toBe("ready")
    expect(store().answers?.deathDate).toBe("2026-10-01")
    expect(store().entrySource).toBe("restored")
    expect(store().procedureStates.p05).toEqual({ guidanceRead: true, needsRecheck: true })
  })

  it("복원한 위험 답변은 [그대로 맞음]을 누르기 전까지 미확인이다(D-09)", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    store().answerRisk("debt", "yes")
    await grantChecklistStorage(db)

    await reload()

    expect(store().riskAnswers.debt).toEqual({ riskId: "debt", answer: "yes", confirmed: false })
    store().confirmRisk("debt")
    expect(store().riskAnswers.debt?.confirmed).toBe(true)
  })

  it("메모리에 이미 답이 있으면(카카오 인계 직후 등) 저장 기록으로 덮어쓰지 않는다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    await grantChecklistStorage(db)
    await persistence.flush()
    persistence.stop()

    store().reset()
    store().setInitialAnswers({ ...ANSWERS, relationship: "spouse" }, "kakao")
    await start()

    expect(store().answers?.relationship).toBe("spouse")
    expect(store().entrySource).toBe("kakao")
  })
})

describe("저장 실패(D-10, 4-2-4)", () => {
  it("IndexedDB를 쓸 수 없으면 '저장 불가'로 시작하고 메모리 이용은 계속된다", async () => {
    // 전역 IndexedDB가 없는 Node 환경 그대로 → 사생활 보호 모드 등 미지원 상황
    db = new InheritanceDb("unsupported")
    await start()
    expect(status()).toBe("failed")

    store().setInitialAnswers(ANSWERS, "direct")
    expect(store().answers).toEqual(ANSWERS)
  })

  it("동의 직후 저장이 실패하면 '저장 중'을 표시하지 않는다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    vi.spyOn(db.checklists, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )

    await grantChecklistStorage(db)

    expect(status()).toBe("failed")
    expect(store().answers).toEqual(ANSWERS)
  })

  it("저장 중 상태에서 이후 저장이 실패하면 '저장 불가'로 바뀌고 메모리 상태는 유지된다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    await grantChecklistStorage(db)
    vi.spyOn(db.checklists, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )

    store().setGuidanceRead("p02", true)
    await persistence.flush()

    expect(status()).toBe("failed")
    expect(store().procedureStates.p02.guidanceRead).toBe(true)
  })
})

describe("리뷰 회귀: 저장 중 변경·실패 표시", () => {
  it("동의 처리 중(데이터를 쓰는 순간) 바꾼 내용도 빠짐없이 저장된다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    const originalPut = db.checklists.put.bind(db.checklists)
    vi.spyOn(db.checklists, "put").mockImplementationOnce((...args) => {
      // 첫 저장이 진행되는 사이에 사용자가 다른 절차를 확인한다.
      store().setGuidanceRead("p03", true)
      return originalPut(...args)
    })

    await grantChecklistStorage(db)
    vi.restoreAllMocks()
    await reload()

    expect(store().procedureStates.p03.guidanceRead).toBe(true)
  })

  it("동의는 됐지만 데이터 저장이 실패하면, 다시 접속해도 '저장 중'으로 표시하지 않는다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    vi.spyOn(db.checklists, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )
    await grantChecklistStorage(db)
    expect(status()).toBe("failed")
    vi.restoreAllMocks()

    await reload()

    expect(status()).not.toBe("ready")
    expect(await db.checklists.count()).toBe(0)
  })

  it("다시 접속했을 때 실제로 쓸 수 없으면 '저장 중' 대신 '저장 불가'를 표시한다", async () => {
    await start()
    store().setInitialAnswers(ANSWERS, "direct")
    await grantChecklistStorage(db)
    await persistence.flush()
    persistence.stop()
    store().reset()
    vi.spyOn(db.checklists, "put").mockRejectedValue(
      new DOMException("저장 공간 부족", "QuotaExceededError"),
    )

    await start()
    await persistence.flush()

    expect(status()).toBe("failed")
    // 복원한 내용으로 메모리 이용은 계속된다.
    expect(store().answers).toEqual(ANSWERS)
  })
})
