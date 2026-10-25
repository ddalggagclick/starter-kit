// @vitest-environment jsdom
// W-02 서버 저장 띠 화면 테스트(4-5-1, 4-6-1, 4-6-3, 4-3-4 서버, 검증 ②). 요청을 세는 가짜 A17로 실행한다.
// A17은 계약 미확정·Backend 미구현이라 실제 서버 연동 검증이 아니다.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import type { ChecklistSnapshot } from "@/shared/storage/db"
import { type ServerChecklistSync, startServerChecklistSync } from "./server-checklist"
import type { ServerChecklistApi } from "./server-checklist-api"
import { ServerSaveBand } from "./server-save-band"

const SPOUSE: InitialAnswers = {
  relationship: "spouse",
  deathDate: null,
  deathDateUnknown: true,
  oneStopApplication: "no",
}

const fakeApi = (read: { consent: boolean; snapshot: ChecklistSnapshot | null }) => {
  const fail = { remove: false }
  const api = {
    read: vi.fn(async () => read),
    save: vi.fn(async () => {}),
    remove: vi.fn(async () => {
      if (fail.remove) throw new Error("remove")
    }),
  } satisfies ServerChecklistApi
  return { api, fail }
}

let sync: ServerChecklistSync | null = null

const startAs = async (accountId: string, api: ServerChecklistApi) => {
  act(() => useAuthStore.getState().signIn({ accountId, email: null }))
  sync = startServerChecklistSync(accountId, api)
  await act(() => sync?.ready ?? Promise.resolve())
}

beforeEach(() => {
  useAuthStore.getState().signOut()
  useInheritanceStore.getState().reset()
  useInheritanceStore.getState().setInitialAnswers(SPOUSE, "direct")
})
afterEach(() => {
  sync?.stop()
  sync = null
  cleanup()
})

describe("ServerSaveBand", () => {
  it("비로그인이면 보이지 않는다", () => {
    startServerChecklistSync(null, null)
    const { container } = render(<ServerSaveBand />)
    expect(container.textContent).toBe("")
  })

  it("다른 계정의 서버 저장 상태는 보이지 않는다", async () => {
    await startAs("user-a", fakeApi({ consent: false, snapshot: null }).api)
    act(() => useAuthStore.getState().signIn({ accountId: "user-b", email: null }))

    const { container } = render(<ServerSaveBand />)
    expect(container.textContent).toBe("")
  })

  it("동의 전에는 정책 확인을 체크해야 [서버에 저장]할 수 있고, 저장하면 상태를 표시한다", async () => {
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    render(<ServerSaveBand />)

    const save = screen.getByRole("button", { name: "서버에 저장" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText("서버 저장 정책을 확인했습니다"))
    fireEvent.click(save)

    await waitFor(() => expect(screen.getByText(/계정\(서버\)에 저장 중/)).toBeTruthy())
    expect(api.save).toHaveBeenCalledTimes(1)
  })

  it("서버 기록이 있으면 자동으로 합치지 않고 고르게 하며, [서버 기록 불러오기]로 화면을 바꾼다", async () => {
    const record: ChecklistSnapshot = {
      answers: { ...SPOUSE, relationship: "sibling" },
      riskAnswers: {},
      procedureStates: {} as ChecklistSnapshot["procedureStates"],
    }
    await startAs("user-a", fakeApi({ consent: true, snapshot: record }).api)
    render(<ServerSaveBand />)

    expect(screen.getByText(/자동으로 합치지 않으니/)).toBeTruthy()
    expect(useInheritanceStore.getState().answers?.relationship).toBe("spouse")
    expect(screen.getByRole("button", { name: "이 기기 내용으로 서버 덮어쓰기" })).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "서버 기록 불러오기" }))

    expect(useInheritanceStore.getState().answers?.relationship).toBe("sibling")
    expect(screen.queryByRole("button", { name: "서버 기록 불러오기" })).toBeNull()
  })

  it("서버 철회가 실패하면 서버에 기록이 남았다고 알리고 [서버 삭제 다시 시도]로 다시 지운다 (검증 ②)", async () => {
    const { api, fail } = fakeApi({ consent: true, snapshot: null })
    await startAs("user-a", api)
    render(<ServerSaveBand />)
    fail.remove = true

    fireEvent.click(screen.getByRole("button", { name: "서버 저장 철회" }))
    fireEvent.click(screen.getByRole("button", { name: "철회하고 서버 기록 삭제" }))

    await waitFor(() => expect(screen.getByText(/서버에 체크리스트 기록이 남아 있고/)).toBeTruthy())
    fail.remove = false
    fireEvent.click(screen.getByRole("button", { name: "서버 삭제 다시 시도" }))

    await waitFor(() =>
      expect(screen.getByText(/서버의 체크리스트 기록을 삭제했습니다/)).toBeTruthy(),
    )
    expect(api.remove).toHaveBeenCalledTimes(2)
  })
})
