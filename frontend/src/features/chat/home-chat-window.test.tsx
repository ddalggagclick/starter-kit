// @vitest-environment jsdom
// 첫 화면 AI 대화창 화면 시험(#210): 실제 라우터(appRoutes) + Mock A08 + 메모리 IndexedDB.
// 실제 브라우저·Backend 검증이 아니다. Mock 답변은 이벤트마다 지연이 있어 몇 초씩 걸린다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { resetMockApiState } from "@/mocks/mock-api"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { inheritanceDb } from "@/shared/storage/db"
import { MAX_MANUAL_RETRIES } from "./chat-page"
import { useChatSessionStore } from "./chat-store"

const ANSWER_TIMEOUT = { timeout: 6000 }

const renderHome = () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/"] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

const chatWindow = () => screen.getByRole("region", { name: "AI에게 질문하기" })
const conversation = () => screen.getByRole("region", { name: "대화" })

// 질문을 보내고 Mock 답변(타이핑 완료 후 출처까지)이 대화창 안에 보일 때까지 기다린다.
const ask = async (question: string) => {
  fireEvent.change(within(chatWindow()).getByLabelText("질문"), { target: { value: question } })
  fireEvent.click(within(chatWindow()).getByRole("button", { name: "보내기" }))
  await waitFor(
    () => expect(within(conversation()).getByText("공식 출처")).toBeTruthy(),
    ANSWER_TIMEOUT,
  )
}

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  useMockAiScenarioStore.setState({ scenario: "answered" })
})
afterEach(cleanup)

describe("첫 화면 구성 (#210)", () => {
  it("배너 아래에 AI 대화창이 있고, [AI에게 질문하기] 카드는 없으며 나머지 카드 3개는 남는다", async () => {
    renderHome()

    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy()
    const window = await screen.findByRole("region", { name: "AI에게 질문하기" })
    expect(within(window).getByRole("heading", { level: 2, name: "AI에게 질문하기" })).toBeTruthy()
    expect(within(window).getByText("궁금한 것을 물어보세요.")).toBeTruthy()
    // 헤더 메뉴가 찾아올 위치
    expect(window.closest("#ai")).toBeTruthy()

    const shortcuts = screen.getByRole("region", { name: "안내 바로가기" })
    expect(within(shortcuts).getAllByRole("link")).toHaveLength(3)
    expect(within(shortcuts).getByText("전체 절차 보기")).toBeTruthy()
    expect(within(shortcuts).getByText("상속 관계 알아보기")).toBeTruthy()
    expect(within(shortcuts).getByText("상속세 기본 안내")).toBeTruthy()
    expect(screen.queryByText("AI에게 질문하기", { selector: "[data-slot=card-title]" })).toBeNull()
    expect(screen.queryByText("공식 근거와 함께 답합니다.")).toBeNull()
  })
})

describe("첫 화면에서 대화 (#210)", () => {
  it("질문을 보내면 대화창 안에 답변과 출처가 나오고, 첫 화면을 떠나지 않는다", async () => {
    const router = renderHome()
    await ask("상속포기 기한")

    expect(within(conversation()).getByText("상속포기 기한")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/")
    expect(within(chatWindow()).getByText(/오늘 남은 질문 9회/)).toBeTruthy()
  }, 15_000)

  it(`기술 오류(S6)는 대화창 안에 안내와 [다시 시도]를 보이고, ${MAX_MANUAL_RETRIES}회 뒤에는 막는다`, async () => {
    useMockAiScenarioStore.setState({ scenario: "providerUnavailable" })
    renderHome()
    fireEvent.change(within(chatWindow()).getByLabelText("질문"), { target: { value: "실패" } })
    fireEvent.click(within(chatWindow()).getByRole("button", { name: "보내기" }))

    expect(
      await within(conversation()).findByText("일시적인 문제로 답변하지 못했습니다."),
    ).toBeTruthy()
    for (let attempt = 0; attempt < MAX_MANUAL_RETRIES; attempt += 1) {
      fireEvent.click(await within(conversation()).findByRole("button", { name: "다시 시도" }))
    }
    expect(
      await within(conversation()).findByText(/다시 시도 횟수\(3회\)를 모두 사용했습니다/),
    ).toBeTruthy()
    // 실패한 질문은 대화에 한 번만 남는다.
    expect(within(conversation()).getAllByText("실패")).toHaveLength(1)
  })

  it("저장하지 않은 대화가 있을 때 다른 메뉴로 가면 확인창을 띄우고, [저장 없이 이동]하면 이동한다(S11)", async () => {
    const router = renderHome()
    await ask("저장 안 한 질문")

    fireEvent.click(screen.getByRole("link", { name: "체크리스트" }))

    expect(await screen.findByText("이 대화는 저장되지 않아 나가면 사라집니다.")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/")
    fireEvent.click(screen.getByRole("button", { name: "저장 없이 이동" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
  }, 15_000)

  it("저장에 동의하면 [이전 대화]가 생기고, 열면 목록과 삭제·철회 버튼이 보인다", async () => {
    renderHome()
    await ask("저장할 질문")

    fireEvent.click(within(chatWindow()).getByRole("button", { name: "저장 설정" }))
    fireEvent.click(screen.getByLabelText("AI 대화 저장 정책을 확인했습니다"))
    fireEvent.click(screen.getByRole("button", { name: "저장" }))
    const history = await within(chatWindow()).findByRole("button", { name: /이전 대화/ })
    // 닫혀 있을 때는 삭제·철회 버튼이 없다(위쪽 줄을 단순하게).
    expect(screen.queryByRole("button", { name: "대화 기록 삭제" })).toBeNull()

    fireEvent.click(history)

    const list = await screen.findByRole("list", { name: "이전 대화" })
    await waitFor(() => expect(within(list).getByText(/저장할 질문/)).toBeTruthy())
    expect(screen.getByRole("button", { name: "대화 기록 삭제" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "AI 대화 저장 동의 철회" })).toBeTruthy()
  }, 15_000)
})
