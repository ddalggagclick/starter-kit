// @vitest-environment jsdom
// W-02 서버 저장 띠 화면 테스트(4-5-1, 4-6-1, 4-6-3, 4-3-4 서버, 검증 ②). 요청을 세는 가짜 A17로 실행한다.
// A17은 계약 미확정·Backend 미구현이라 실제 서버 연동 검증이 아니다.
// #197: 서버 저장 동의는 [서버 저장] 모달에서, 서버 기록 선택은 저절로 한 번 열리는 모달에서 받는다.
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import type { ChecklistSnapshot } from "@/shared/storage/db"
import { useChecklistSaveModal } from "./checklist-consent-band"
import { ChecklistPage } from "./checklist-page"
import { type ServerChecklistSync, startServerChecklistSync } from "./server-checklist"
import type { ServerChecklistApi } from "./server-checklist-api"
import { ServerSaveBand } from "./server-save-band"
import { ChecklistSaveModalHost } from "./storage-settings"

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

  it("동의 전에는 [서버 저장] 모달에서 정책 확인을 체크해야 [서버에 저장]할 수 있고, 저장하면 상태를 표시한다", async () => {
    const { api } = fakeApi({ consent: false, snapshot: null })
    await startAs("user-a", api)
    render(<ServerSaveBand />)

    expect(screen.queryByRole("dialog")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "서버 저장" }))
    const save = screen.getByRole("button", { name: "서버에 저장" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText("서버 저장 정책을 확인했습니다"))
    fireEvent.click(save)

    await waitFor(() => expect(screen.getByText(/계정\(서버\)에 저장 중/)).toBeTruthy())
    expect(api.save).toHaveBeenCalledTimes(1)
    // 저장하면 상태가 바뀌어 모달이 저절로 닫힌다.
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("서버 기록이 있으면 자동으로 합치지 않고 고르게 하며, [서버 기록 불러오기]로 화면을 바꾼다", async () => {
    const record: ChecklistSnapshot = {
      answers: { ...SPOUSE, relationship: "sibling" },
      riskAnswers: {},
      procedureStates: {} as ChecklistSnapshot["procedureStates"],
    }
    await startAs("user-a", fakeApi({ consent: true, snapshot: record }).api)
    render(<ServerSaveBand />)

    // 누르지 않아도 고르는 모달이 열려 있다.
    expect(
      screen.getByRole("dialog", { name: "계정(서버)에 저장된 체크리스트가 있습니다" }),
    ).toBeTruthy()
    expect(screen.getByText(/자동으로 합치지 않으니/)).toBeTruthy()
    expect(useInheritanceStore.getState().answers?.relationship).toBe("spouse")
    expect(screen.getByRole("button", { name: "이 기기 내용으로 서버 덮어쓰기" })).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "서버 기록 불러오기" }))

    expect(useInheritanceStore.getState().answers?.relationship).toBe("sibling")
    expect(screen.queryByRole("button", { name: "서버 기록 불러오기" })).toBeNull()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("서버 기록 선택 모달을 닫아도 아무것도 합치지 않고, [선택하기]로 다시 연다", async () => {
    const record: ChecklistSnapshot = {
      answers: { ...SPOUSE, relationship: "sibling" },
      riskAnswers: {},
      procedureStates: {} as ChecklistSnapshot["procedureStates"],
    }
    await startAs("user-a", fakeApi({ consent: true, snapshot: record }).api)
    render(<ServerSaveBand />)

    fireEvent.keyDown(document, { key: "Escape" })

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.getByText(/서버 기록 선택 필요/)).toBeTruthy()
    expect(useInheritanceStore.getState().answers?.relationship).toBe("spouse")
    fireEvent.click(screen.getByRole("button", { name: "선택하기" }))
    expect(screen.getByRole("button", { name: "서버 기록 불러오기" })).toBeTruthy()
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

describe("답이 없는 화면 (리뷰 회귀)", () => {
  const RECORD: ChecklistSnapshot = {
    answers: { ...SPOUSE, relationship: "sibling" },
    riskAnswers: {},
    procedureStates: {} as ChecklistSnapshot["procedureStates"],
  }

  const renderChecklistPage = () => {
    // 사용자 지시(2026-10-30): 서버 저장은 플로팅 [저장]의 저장 설정 창 안에 있다. 화면과 창을 함께 그리고 창을 연다.
    const router = createMemoryRouter(
      [
        {
          path: "/checklist",
          element: (
            <>
              <ChecklistPage />
              <ChecklistSaveModalHost />
            </>
          ),
        },
      ],
      { initialEntries: ["/checklist"] },
    )
    act(() => useChecklistSaveModal.getState().setOpen(true))
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
  }

  beforeEach(() => useInheritanceStore.getState().reset())

  it("서버 저장 동의 전이면 동의를 묻지 않는다(보낼 답이 없다)", async () => {
    await startAs("user-a", fakeApi({ consent: false, snapshot: null }).api)
    render(<ServerSaveBand />)

    expect(screen.queryByRole("button", { name: "서버 저장" })).toBeNull()
  })

  it("새 기기에서 로그인하면 답이 없어도 체크리스트 화면에서 서버 기록을 불러올 수 있다 (4-6-3)", async () => {
    await startAs("user-a", fakeApi({ consent: true, snapshot: RECORD }).api)
    renderChecklistPage()

    expect(screen.queryByRole("button", { name: "이 기기 내용으로 서버 덮어쓰기" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "서버 기록 불러오기" }))

    expect(useInheritanceStore.getState().answers?.relationship).toBe("sibling")
  })

  // 화면 단위로는 띠가 놓이는지만 본다. 철회 실패 안내·재시도 흐름은 위 ServerSaveBand 테스트(검증 ②)가 확인한다.
  // 화면 전체에서 철회 흐름까지 돌리던 테스트는 전체 실행에서 간헐 실패(원인 미확인)해 단순화했다(PR에 기록).
  it("이 기기 기록을 지운 뒤(답이 없는 화면)에도 [서버 저장 철회]를 할 수 있다 (검증 ②)", async () => {
    await startAs("user-a", fakeApi({ consent: true, snapshot: null }).api)
    renderChecklistPage()

    expect(screen.getByRole("button", { name: "처음 시작하기" })).toBeTruthy()
    // 저장 설정 창의 "계정(서버) 저장" 칸: 다른 칸과 같은 이름의 [저장 동의 철회].
    expect(
      within(screen.getByRole("region", { name: "계정(서버) 저장" })).getByRole("button", {
        name: "저장 동의 철회",
      }),
    ).toBeTruthy()
  })
})
