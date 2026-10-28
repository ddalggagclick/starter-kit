// @vitest-environment jsdom
// 검증 ① 계정 격리(4-2-2, 5-3-3): A 로그인 → 저장 → 로그아웃 → B 로그인 → A 기록 미노출, 새로고침 후에도 동일.
// 실제 저장 훅(useChecklistPersistence)과 fake-indexeddb로 실행한다. "새로고침"은 훅을 내리고 메모리를 비운 뒤 다시 띄워 흉내 낸다.
// 실제 브라우저·Backend 로그인 검증을 대신하지 않는다.
import { act, renderHook, waitFor } from "@testing-library/react"
import axios, { type AxiosAdapter } from "axios"
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import { AUTH_WIRE, accessSession, attachAuthSecurity } from "@/shared/api/auth"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import {
  accountNamespace,
  GUEST_NAMESPACE,
  InheritanceDb,
  loadChecklist,
} from "@/shared/storage/db"
import { grantChecklistStorage, useChecklistStorageStore } from "./checklist-storage"
import { useChecklistPersistence } from "./use-checklist-persistence"

const ACCOUNT_A = { accountId: "user-a", email: "a@example.com" }
const ACCOUNT_B = { accountId: "user-b", email: "b@example.com" }
const A_ANSWERS: InitialAnswers = {
  relationship: "spouse",
  deathDate: "2026-09-30",
  deathDateUnknown: false,
  oneStopApplication: "yes",
}

const memory = () => useInheritanceStore.getState()
const auth = () => useAuthStore.getState()
const status = () => useChecklistStorageStore.getState().status

let db: InheritanceDb

const mount = () => renderHook(() => useChecklistPersistence(db))
const settled = () => waitFor(() => expect(status()).not.toBe("checking"))

// A로 로그인해 답하고 저장에 동의한 뒤, 실제로 A 영역에 기록될 때까지 기다린다.
const saveAsA = async () => {
  act(() => auth().signIn(ACCOUNT_A))
  await settled()
  act(() => {
    memory().setInitialAnswers(A_ANSWERS, "direct")
    memory().setGuidanceRead("p01", true)
  })
  await act(() => grantChecklistStorage(db))
  await waitFor(async () => {
    const saved = await loadChecklist(db, accountNamespace("user-a"))
    expect(saved.ok && saved.value?.procedureStates.p01.guidanceRead).toBe(true)
  })
}

beforeEach(() => {
  db = new InheritanceDb("isolation-test", { indexedDB: new IDBFactory(), IDBKeyRange })
  memory().reset()
  auth().signOut()
})

afterEach(() => {
  db.close()
  accessSession.clear()
})

describe("계정 격리 (검증 ①)", () => {
  it("A 저장 → 로그아웃 → B 로그인: A 기록이 보이지 않고, 새로고침 뒤에도 같다", async () => {
    const hook = mount()
    await settled()
    await saveAsA()

    // 로그아웃: 화면에서 A 기록이 사라진다(기록은 지우지 않고 숨김).
    act(() => auth().signOut())
    await settled()
    expect(memory().answers).toBeNull()
    expect(memory().procedureStates.p01.guidanceRead).toBe(false)

    // B 로그인: A 기록이 복원되지 않는다.
    act(() => auth().signIn(ACCOUNT_B))
    await settled()
    expect(status()).toBe("not-consented")
    expect(memory().answers).toBeNull()

    // 새로고침(B 로그인 유지): 여전히 A 기록이 보이지 않는다.
    hook.unmount()
    memory().reset()
    mount()
    await settled()
    expect(memory().answers).toBeNull()

    // A 기록은 A 영역에만 있고 Guest·B 영역에는 없다.
    expect(await loadChecklist(db, accountNamespace("user-b"))).toEqual({ ok: true, value: null })
    expect(await loadChecklist(db, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("B로 쓰는 동안 저장은 B 영역에만 가고, A로 다시 로그인하면 A 기록만 복원된다", async () => {
    mount()
    await settled()
    await saveAsA()

    act(() => auth().signOut())
    await settled()
    act(() => auth().signIn(ACCOUNT_B))
    await settled()
    act(() => memory().setInitialAnswers({ ...A_ANSWERS, relationship: "sibling" }, "direct"))
    await act(() => grantChecklistStorage(db))
    await waitFor(async () => {
      const saved = await loadChecklist(db, accountNamespace("user-b"))
      expect(saved.ok && saved.value?.answers?.relationship).toBe("sibling")
    })

    act(() => auth().signOut())
    await settled()
    act(() => auth().signIn(ACCOUNT_A))
    await waitFor(() => expect(memory().answers?.relationship).toBe("spouse"))
    expect(memory().procedureStates.p01.guidanceRead).toBe(true)
    expect(memory().entrySource).toBe("restored")
  })

  it("Refresh 실패로 인증이 끊기면(5-3-3) 계정 화면 데이터가 사라진다", async () => {
    mount()
    await settled()
    await saveAsA()

    // 모든 요청 401, Refresh도 401(REFRESH_INVALID)인 서버
    const adapter: AxiosAdapter = async (config) => {
      const ok = config.url === AUTH_WIRE.csrfPath
      const response = {
        data: ok ? { csrfToken: "csrf" } : { code: "REFRESH_INVALID" },
        status: ok ? 200 : 401,
        statusText: "",
        headers: {},
        config,
      }
      if (!ok) throw Object.assign(new Error("401"), { config, response })
      return response
    }
    const api = axios.create({ adapter })
    attachAuthSecurity(api, AUTH_WIRE)
    accessSession.set("expired")

    await act(async () => {
      await api.get("/api/anything").catch(() => undefined)
    })

    await waitFor(() => expect(auth().accountId).toBeNull())
    await settled()
    expect(memory().answers).toBeNull()
  })
})
