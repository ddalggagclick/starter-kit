// @vitest-environment jsdom
// 4-6-1 화면 검증: 체크리스트 화면에서 이 기기 저장 동의와 서버(계정) 저장 동의가 따로 보이고 서로 영향을 주지 않는다.
// 실제 화면 + 메모리 IndexedDB + 요청을 세는 가짜 A17. 실제 서버 연동 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { loadConsentStatuses } from "@/shared/storage/consent"
import { accountNamespace, inheritanceDb, loadChecklist } from "@/shared/storage/db"
import { ChecklistPage } from "./checklist-page"
import { type ChecklistPersistence, startChecklistPersistence } from "./checklist-storage"
import {
  revokeServerSave,
  type ServerChecklistSync,
  startServerChecklistSync,
} from "./server-checklist"
import type { ServerChecklistApi } from "./server-checklist-api"

const ACCOUNT = "user-a"
const NAMESPACE = accountNamespace(ACCOUNT)
const SPOUSE: InitialAnswers = {
  relationship: "spouse",
  deathDate: null,
  deathDateUnknown: true,
  oneStopApplication: "no",
}

let local: ChecklistPersistence
let sync: ServerChecklistSync
let api: ServerChecklistApi & {
  save: ReturnType<typeof vi.fn>
  remove: ReturnType<typeof vi.fn>
}

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  useInheritanceStore.getState().reset()
  act(() => useAuthStore.getState().signIn({ accountId: ACCOUNT, email: null }))
  api = {
    read: vi.fn(async () => ({ consent: false, snapshot: null })),
    save: vi.fn(async () => {}),
    remove: vi.fn(async () => {}),
  }
  local = startChecklistPersistence(inheritanceDb, NAMESPACE)
  sync = startServerChecklistSync(ACCOUNT, api)
  await act(async () => {
    await local.ready
    await sync.ready
  })
  act(() => useInheritanceStore.getState().setInitialAnswers(SPOUSE, "direct"))
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider
        router={createMemoryRouter([{ path: "/checklist", element: <ChecklistPage /> }], {
          initialEntries: ["/checklist"],
        })}
      />
    </QueryClientProvider>,
  )
})
afterEach(() => {
  sync.stop()
  local.stop()
  cleanup()
  useAuthStore.getState().signOut()
})

const localBand = () => screen.getByRole("region", { name: "체크리스트 저장" })
const serverBand = () => screen.getByRole("region", { name: "서버 저장" })
// #197: 두 동의 모두 버튼을 눌러 여는 모달에서 받는다. 모달은 각 띠(region) 안에 그려진다.
const openLocal = () =>
  fireEvent.click(within(localBand()).getByRole("button", { name: "저장 설정" }))
const openServer = () =>
  fireEvent.click(within(serverBand()).getByRole("button", { name: "서버 저장 설정" }))

describe("이 기기 저장 동의와 서버 저장 동의의 독립 (4-6-1)", () => {
  it("두 동의가 따로 보이고, [서버에 저장]을 눌러도 이 기기 저장 동의는 그대로다", async () => {
    expect(within(localBand()).getByRole("button", { name: "저장 설정" })).toBeTruthy()
    openServer()
    fireEvent.click(within(serverBand()).getByLabelText("서버 저장 정책을 확인했습니다"))
    fireEvent.click(within(serverBand()).getByRole("button", { name: "서버에 저장" }))

    expect(await screen.findByText(/계정\(서버\)에 저장 중/)).toBeTruthy()
    expect(api.save).toHaveBeenCalledTimes(1)
    // 이 기기 쪽은 여전히 동의를 묻고, 저장소에도 동의가 없다.
    expect(within(localBand()).getByRole("button", { name: "저장 설정" })).toBeTruthy()
    expect((await loadConsentStatuses(inheritanceDb, NAMESPACE)).checklist).toBe("not-consented")
    expect(await loadChecklist(inheritanceDb, NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("이 기기 저장에 동의해도 서버 저장 동의는 '없음' 그대로이고 서버 저장 요청은 0건이다", async () => {
    openLocal()
    fireEvent.click(within(localBand()).getByLabelText("저장 정책을 확인했습니다"))
    fireEvent.click(within(localBand()).getByRole("button", { name: "저장" }))

    expect(await screen.findByText(/이 기기에 저장 중/)).toBeTruthy()
    expect(within(serverBand()).getByRole("button", { name: "서버 저장 설정" })).toBeTruthy()
    act(() => useInheritanceStore.getState().setGuidanceRead("p01", true))
    await act(() => sync.flush())
    expect(api.save).not.toHaveBeenCalled()
  })

  it("서버 저장을 철회해도 이 기기 저장 동의와 기록은 그대로다", async () => {
    openLocal()
    fireEvent.click(within(localBand()).getByLabelText("저장 정책을 확인했습니다"))
    fireEvent.click(within(localBand()).getByRole("button", { name: "저장" }))
    expect(await screen.findByText(/이 기기에 저장 중/)).toBeTruthy()
    openServer()
    fireEvent.click(within(serverBand()).getByLabelText("서버 저장 정책을 확인했습니다"))
    fireEvent.click(within(serverBand()).getByRole("button", { name: "서버에 저장" }))
    expect(await screen.findByText(/계정\(서버\)에 저장 중/)).toBeTruthy()

    // 철회 확인창 흐름은 server-save-band.test.tsx가 확인한다. 여기서는 철회 결과가 이 기기 쪽에 번지지 않는지만 본다.
    await act(async () => {
      expect(await revokeServerSave(ACCOUNT)).toBe(true)
    })
    // 철회가 실제로 서버 삭제(A17 DELETE)까지 갔는지 확인한다(리뷰 반영). 서버 띠는 다시 동의를 묻는다.
    expect(api.remove).toHaveBeenCalledTimes(1)
    expect(within(serverBand()).getByRole("button", { name: "서버 저장 설정" })).toBeTruthy()

    expect(screen.getByText(/이 기기에 저장 중/)).toBeTruthy()
    expect((await loadConsentStatuses(inheritanceDb, NAMESPACE)).checklist).toBe("ready")
    const saved = await loadChecklist(inheritanceDb, NAMESPACE)
    expect(saved.ok && saved.value?.answers).toEqual(SPOUSE)
  })
})
