// @vitest-environment jsdom
/*
 * 담당: [A] | 책임: 체크리스트 위 플로팅 AI 대화창(UI 전면 개편 지시서 3장) 시험.
 * 확인: 열기·바깥 누르기·[닫기]·Esc로 닫기, 닫아도 대화·체크리스트 상태가 그대로, 초점이 플로팅 버튼으로 돌아옴.
 */
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { useChecklistSaveModal } from "@/features/checklist/checklist-consent-band"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { resetMockApiState } from "@/mocks/mock-api"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { inheritanceDb } from "@/shared/storage/db"
import { useChatSessionStore } from "./chat-store"

const renderChecklist = () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/checklist"] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

const launcher = () => screen.getByRole("button", { name: "AI에게 질문하기" })
// 숨긴 요소는 접근 가능한 이름을 계산하지 않아 속성으로 찾는다.
const panel = () =>
  document.querySelector<HTMLElement>('[role="dialog"][aria-label="AI 대화창"]') as HTMLElement

beforeEach(async () => {
  useChecklistSaveModal.setState({ open: false })
  await inheritanceDb.delete()
  await inheritanceDb.open()
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  useMockAiScenarioStore.setState({ scenario: "answered" })
  useInheritanceStore.getState().setInitialAnswers(
    {
      relationship: "spouse",
      deathDate: null,
      deathDateUnknown: true,
      oneStopApplication: "no",
    },
    "direct",
  )
})
afterEach(cleanup)

describe("체크리스트 플로팅 AI 대화창", () => {
  it("버튼으로 열고, 바깥·[닫기]·Esc로 닫으며, 닫으면 초점이 버튼으로 돌아온다", async () => {
    const router = renderChecklist()
    await screen.findByRole("heading", { name: "지금 확인할 공통 절차" })
    expect(panel().hidden).toBe(true)

    fireEvent.click(launcher())
    expect(panel().hidden).toBe(false)
    expect(router.state.location.pathname).toBe("/checklist")
    const close = within(panel()).getByRole("button", { name: "대화창 닫기" })
    expect(document.activeElement).toBe(close)

    fireEvent.click(close)
    expect(panel().hidden).toBe(true)
    expect(document.activeElement).toBe(launcher())

    fireEvent.click(launcher())
    fireEvent.keyDown(window, { key: "Escape" })
    expect(panel().hidden).toBe(true)

    fireEvent.click(launcher())
    // 바깥(뒤쪽 막)은 대화창 바로 앞 형제 요소다.
    fireEvent.click(panel().previousElementSibling as Element)
    expect(panel().hidden).toBe(true)
    // 체크리스트는 그대로다.
    expect(screen.getByRole("heading", { name: "지금 확인할 공통 절차" })).toBeTruthy()
  })

  it("닫았다 다시 열어도 대화와 읽음 상태가 그대로다", async () => {
    renderChecklist()
    await screen.findByRole("heading", { name: "지금 확인할 공통 절차" })
    useInheritanceStore.getState().setGuidanceRead("p01", true)

    fireEvent.click(launcher())
    const input = within(panel()).getByLabelText("질문")
    fireEvent.change(input, { target: { value: "상속포기 기한" } })
    fireEvent.click(within(panel()).getByRole("button", { name: "보내기" }))
    await waitFor(() => expect(within(panel()).getByText("공식 출처")).toBeTruthy(), {
      timeout: 6000,
    })

    fireEvent.keyDown(window, { key: "Escape" })
    fireEvent.click(launcher())
    expect(within(panel()).getByText("상속포기 기한")).toBeTruthy()
    expect(useInheritanceStore.getState().procedureStates.p01.guidanceRead).toBe(true)
  })
})

describe("플로팅 AI 대화창이 보이는 화면", () => {
  const renderAt = (path: string) => {
    const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    return router
  }

  // 추가 수정 지시서 3장: 위에서부터 [저장]·[AI 질문]·[체크리스트] 한 묶음, 지금 화면 버튼은 표시만(aria-current).
  it("플로팅 내비게이션은 저장·AI·체크리스트 순서이고 화면별로 다르게 동작한다", async () => {
    const nav = () => screen.getByRole("navigation", { name: "빠른 이동" })
    const names = () =>
      within(nav())
        .getAllByRole("button")
        .map((button) => button.getAttribute("aria-label"))
    // /ai: AI는 지금 화면, 체크리스트는 이동
    let router = renderAt("/ai")
    expect(names()).toEqual(["저장 설정", "AI에게 질문하기", "절차 체크리스트"])
    const ai = within(nav()).getByRole("button", { name: "AI에게 질문하기" })
    expect(ai.getAttribute("aria-current")).toBe("page")
    fireEvent.click(within(nav()).getByRole("button", { name: "절차 체크리스트" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    expect(
      within(nav()).getByRole("button", { name: "절차 체크리스트" }).getAttribute("aria-current"),
    ).toBe("page")
    cleanup()

    // 절차 상세: AI는 플로팅 창(페이지 그대로), 체크리스트는 복귀
    router = renderAt("/procedures/p04")
    await screen.findByRole("region", { name: "항상 표시되는 핵심 안내" })
    fireEvent.click(within(nav()).getByRole("button", { name: "AI에게 질문하기" }))
    expect(panel().hidden).toBe(false)
    expect(router.state.location.pathname).toBe("/procedures/p04")
    fireEvent.click(within(panel()).getByRole("button", { name: "대화창 닫기" }))
    // 반복해서 눌러도 창은 하나다.
    fireEvent.click(within(nav()).getByRole("button", { name: "AI에게 질문하기" }))
    fireEvent.click(within(panel()).getByRole("button", { name: "대화창 닫기" }))
    expect(document.querySelectorAll('[aria-label="AI 대화창"]').length).toBe(1)
    fireEvent.click(within(nav()).getByRole("button", { name: "절차 체크리스트" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    cleanup()

    // [저장]은 체크리스트 [저장]과 같은 기존 저장 모달을 연다. 미동의면 "미동의 · 저장 안 됨 · 새로고침하면 사라집니다".
    renderAt("/procedures/p04")
    await screen.findByRole("region", { name: "항상 표시되는 핵심 안내" })
    fireEvent.click(within(nav()).getByRole("button", { name: "저장 설정" }))
    const modal = await screen.findByRole("dialog")
    expect(within(modal).getByRole("region", { name: "이 기기 저장" })).toBeTruthy()
  })

  it("체크리스트를 작성하지 않았으면 [절차 체크리스트]는 질문 3개 창을 연다", () => {
    useInheritanceStore.getState().reset()
    const router = renderAt("/ai")
    fireEvent.click(screen.getByRole("button", { name: "절차 체크리스트" }))
    expect(screen.getByRole("dialog", { name: "상속 절차 시작" })).toBeTruthy()
    expect(router.state.location.pathname).toBe("/ai")
  })

  it("다른 화면으로 이동하면(S11 [저장 없이 이동]) 저장 안 된 대화는 사라진다", async () => {
    const router = renderAt("/checklist")
    await screen.findByRole("heading", { name: "지금 확인할 공통 절차" })
    fireEvent.click(launcher())
    fireEvent.change(within(panel()).getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    fireEvent.click(within(panel()).getByRole("button", { name: "보내기" }))
    await waitFor(() => expect(within(panel()).getByText("공식 출처")).toBeTruthy(), {
      timeout: 6000,
    })
    fireEvent.keyDown(window, { key: "Escape" })

    void router.navigate("/procedures/p04")
    // 이탈 확인이 뜨면 닫혀 있던 창이 다시 열려 확인창이 보인다.
    const confirm = await screen.findByText("이 대화는 저장되지 않아 나가면 사라집니다.")
    await waitFor(() => expect(panel().hidden).toBe(false))
    fireEvent.click(
      within(confirm.closest('[role="alertdialog"], [role="dialog"]') as HTMLElement).getByRole(
        "button",
        { name: "저장 없이 이동" },
      ),
    )
    await waitFor(() => expect(router.state.location.pathname).toBe("/procedures/p04"))
    fireEvent.click(launcher())
    expect(within(panel()).queryByText("상속포기 기한")).toBeNull()
    expect(within(panel()).getByText("궁금한 것을 물어보세요.")).toBeTruthy()
  })
})

describe("저장은 플로팅 [저장 설정]에서만 (사용자 지시 2026-10-30)", () => {
  it("체크리스트 화면에는 저장 UI가 없고, 플로팅 [저장 설정] 창 하나에 이 기기·서버·AI 대화 저장이 모여 있다", async () => {
    const router = createMemoryRouter(appRoutes, { initialEntries: ["/checklist"] })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await screen.findByRole("heading", { name: "지금 확인할 공통 절차" })
    expect(screen.queryByRole("region", { name: "체크리스트 저장" })).toBeNull()
    // [체크리스트 삭제]는 목록 아래에 늘 보이지만, 저장된 기록이 없으면 누를 수 없다(사용자 지시).
    const deleteButton = screen.getByRole("button", {
      name: "체크리스트 삭제",
    }) as HTMLButtonElement
    expect(deleteButton.disabled).toBe(true)
    expect(screen.getByText("기기에 저장된 기록이 있을 때 지울 수 있어요.")).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    const modal = screen.getByRole("dialog", { name: "저장 설정" })
    const device = within(modal).getByRole("region", { name: "이 기기 저장" })
    await within(device).findByText("미동의", { selector: "[role=status]" })
    expect(within(device).getByText("저장 안 됨 · 새로고침하면 사라집니다.")).toBeTruthy()
    // 비로그인이면 서버 칸은 안내만 보인다.
    expect(within(modal).getByRole("region", { name: "계정(서버) 저장" })).toBeTruthy()
    expect(within(modal).getByText("로그인하면 사용할 수 있어요.")).toBeTruthy()
    // 체크리스트 화면에는 (숨겨진) 플로팅 대화창이 있어 AI 대화 칸도 보인다.
    expect(await within(modal).findByRole("region", { name: "AI 대화 저장" })).toBeTruthy()
    expect(screen.getAllByRole("dialog", { name: "저장 설정" }).length).toBe(1)

    // 세 칸은 같은 구조: 제목·상태 표시·정책 전체 목록이 있고, 동의 전 칸은 같은 [저장 안 함]·[저장]을 쓴다.
    for (const name of ["이 기기 저장", "계정(서버) 저장", "AI 대화 저장"]) {
      const section = within(modal).getByRole("region", { name })
      expect(within(section).getByRole("heading", { level: 3 })).toBeTruthy()
      expect(within(section).getByRole("status")).toBeTruthy()
      expect(within(section).getAllByRole("listitem").length).toBeGreaterThanOrEqual(4)
    }
    for (const name of ["이 기기 저장", "AI 대화 저장"]) {
      const section = within(modal).getByRole("region", { name })
      expect(within(section).getByRole("button", { name: "저장 안 함" })).toBeTruthy()
      expect(within(section).getByRole("button", { name: "저장" })).toBeTruthy()
    }
    // 칸 사이 두 줄 구분선(칸 3개 → 구분선 2곳 × 2줄).
    expect(modal.querySelectorAll("hr").length).toBe(4)
  })
})
