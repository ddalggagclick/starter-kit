// @vitest-environment jsdom
// 첫 화면 AI 대화창 화면 시험(#210): 실제 라우터(appRoutes) + Mock A08 + 메모리 IndexedDB.
// 실제 브라우저·Backend 검증이 아니다. Mock 답변은 이벤트마다 지연이 있어 몇 초씩 걸린다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { StrictMode } from "react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { resetEntryGatewayForTest } from "@/features/checklist/entry-gateway"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { resetMockApiState } from "@/mocks/mock-api"
import { PRIVACY_WARNING } from "@/shared/content/chat"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { inheritanceDb } from "@/shared/storage/db"
import { EXTERNAL_TRANSFER_NOTICE, MAX_MANUAL_RETRIES } from "./chat-parts"
import { useChatStorageBridge } from "./chat-storage-bridge"
import { useChatSessionStore } from "./chat-store"

const ANSWER_TIMEOUT = { timeout: 6000 }

const renderHome = () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/ai"] })
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

describe("첫 화면 진입 선택 창 (추가 수정 지시서 1·2장)", () => {
  const renderLanding = () => {
    const router = createMemoryRouter(appRoutes, { initialEntries: ["/"] })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    return router
  }
  beforeEach(resetEntryGatewayForTest)

  it("처음 들어오면 첫 화면 위에 같은 모양의 카드 2개 창이 뜨고, 첫 화면 안에는 카드 영역이 없다", () => {
    renderLanding()
    const title = screen.getAllByRole("heading", { level: 1 })[0]
    expect(title.textContent).toBe("무엇부터 해야 할지함께 확인하세요.")
    const gateway = screen.getByRole("dialog", { name: "시작 방법 선택" })
    const checklist = within(gateway).getByRole("button", { name: /체크리스트로 시작하기/ })
    const ai = within(gateway).getByRole("link", { name: /AI에게 질문하기/ })
    expect(checklist.className).toBe(ai.className)
    expect(screen.queryByRole("region", { name: "시작 방법" })).toBeNull()
    expect(screen.queryByRole("region", { name: "AI에게 질문하기" })).toBeNull()
  })

  it("[체크리스트로 시작하기]는 질문 3개 창으로 바뀌고, 닫은 뒤 첫 화면에 돌아와도 다시 뜨지 않는다", async () => {
    const router = renderLanding()
    fireEvent.click(screen.getByRole("button", { name: /체크리스트로 시작하기/ }))
    expect(screen.getByRole("dialog", { name: "상속 절차 시작" })).toBeTruthy()
    expect(screen.queryByRole("dialog", { name: "시작 방법 선택" })).toBeNull()
    fireEvent.keyDown(window, { key: "Escape" })
    await router.navigate("/ai")
    await router.navigate("/")
    expect(screen.queryByRole("dialog", { name: "시작 방법 선택" })).toBeNull()
  })

  // 개발 서버는 StrictMode라 효과가 두 번 실행된다. 그래도 진입 창이 닫히지 않아야 한다(회귀).
  it("StrictMode(개발 모드)에서도 처음 들어오면 진입 선택 창이 보인다", () => {
    render(
      <StrictMode>
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/"] })} />
        </QueryClientProvider>
      </StrictMode>,
    )
    expect(screen.getByRole("dialog", { name: "시작 방법 선택" })).toBeTruthy()
  })

  it("[AI에게 질문하기]는 /ai로 가고 창이 닫힌다", async () => {
    const router = renderLanding()
    fireEvent.click(screen.getByRole("link", { name: /AI에게 질문하기/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/ai"))
    expect(screen.queryByRole("dialog", { name: "시작 방법 선택" })).toBeNull()
    expect(screen.getByRole("region", { name: "AI에게 질문하기" })).toBeTruthy()
  })
})

describe("질문창 키 입력 (UI 전면 개편)", () => {
  it("Enter는 보내고, Shift+Enter·한글 조합 중 Enter는 보내지 않으며, 빈 입력은 보내지 않는다", async () => {
    renderHome()
    const input = within(chatWindow()).getByLabelText("질문")
    fireEvent.keyDown(input, { key: "Enter" })
    expect(screen.getByRole("alert").textContent).toBe("질문을 입력해 주세요.")
    fireEvent.change(input, { target: { value: "상속포기 기한" } })
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true })
    fireEvent.keyDown(input, { key: "Enter", isComposing: true })
    expect((input as HTMLTextAreaElement).value).toBe("상속포기 기한")
    fireEvent.keyDown(input, { key: "Enter" })
    expect((input as HTMLTextAreaElement).value).toBe("")
    await waitFor(
      () => expect(within(conversation()).getByText("공식 출처")).toBeTruthy(),
      ANSWER_TIMEOUT,
    )
  })
})

describe("대화창 새 모양 (#227, 동작은 그대로)", () => {
  it("개인정보 경고와 외부 전송 안내가 한 줄로 보이고, [확인] 전에는 보낼 수 없으며 [확인] 뒤에는 경고만 남는다", () => {
    useChatSessionStore.setState({ externalNoticeAcknowledged: false })
    renderHome()
    const window = chatWindow()
    fireEvent.change(within(window).getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    const send = within(window).getByRole("button", { name: "보내기" }) as HTMLButtonElement

    expect(within(window).getByText(PRIVACY_WARNING)).toBeTruthy()
    expect(within(window).getByText(EXTERNAL_TRANSFER_NOTICE)).toBeTruthy()
    expect(send.disabled).toBe(true)

    fireEvent.click(within(window).getByRole("button", { name: "확인" }))

    expect(within(window).getByText(PRIVACY_WARNING)).toBeTruthy()
    expect(within(window).queryByText(EXTERNAL_TRANSFER_NOTICE)).toBeNull()
    expect(within(window).queryByRole("button", { name: "확인" })).toBeNull()
    expect(send.disabled).toBe(false)
  })

  // 사용자 지시(2026-10-30): AI 대화 저장은 플로팅 [저장 설정] 모달 안에서만. 대화창 위쪽 줄에는 저장 설정이 없다.
  it("AI 대화 저장은 플로팅 [저장 설정] 모달에서 '저장 안 됨'(점선) → 동의 → '저장 중'(초록)으로 바뀐다", async () => {
    renderHome()
    expect(within(chatWindow()).queryByRole("button", { name: "저장 설정" })).toBeNull()
    expect(within(chatWindow()).queryByRole("region", { name: "AI 대화 저장" })).toBeNull()
    await waitFor(() =>
      expect(useChatStorageBridge.getState().current?.status).toBe("not-consented"),
    )
    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    const section = await screen.findByRole("region", { name: "AI 대화 저장" })
    const off = within(section).getByText("미동의", { selector: "[role=status]" })
    expect(off.className).toContain("border-dashed")
    expect(off.textContent).toBe("AI 대화 미동의")

    fireEvent.click(within(section).getByLabelText("AI 대화 저장 정책을 확인했습니다"))
    fireEvent.click(within(section).getByRole("button", { name: "저장" }))

    const on = await within(section).findByText("저장 중", { selector: "[role=status]" })
    expect(on.className).toContain("bg-success")
    expect(on.textContent).toBe("AI 대화 저장 중")
    expect(within(section).getByRole("button", { name: "저장 동의 철회" })).toBeTruthy()
  })
})

describe("첫 화면에서 대화 (#210)", () => {
  it("질문을 보내면 대화창 안에 답변과 출처가 나오고, 첫 화면을 떠나지 않는다", async () => {
    const router = renderHome()
    await ask("상속포기 기한")

    expect(within(conversation()).getByText("상속포기 기한")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/ai")
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

    // #227 최신 시안: 답하기 전에는 [체크리스트]가 질문 모달을 연다. 페이지 이동(이탈)을 보려고 먼저 답해 둔다.
    act(() => {
      useInheritanceStore.getState().setInitialAnswers(
        {
          relationship: "descendant",
          deathDate: null,
          deathDateUnknown: true,
          oneStopApplication: "no",
        },
        "direct",
      )
    })
    fireEvent.click(screen.getByRole("link", { name: "체크리스트" }))

    expect(await screen.findByText("이 대화는 저장되지 않아 나가면 사라집니다.")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/ai")
    fireEvent.click(screen.getByRole("button", { name: "저장 없이 이동" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
  }, 15_000)

  it("저장에 동의하면 [이전 대화]가 생기고, 열면 목록과 삭제·철회 버튼이 보인다", async () => {
    renderHome()
    await ask("저장할 질문")

    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    const section = await screen.findByRole("region", { name: "AI 대화 저장" })
    fireEvent.click(within(section).getByLabelText("AI 대화 저장 정책을 확인했습니다"))
    fireEvent.click(within(section).getByRole("button", { name: "저장" }))
    await within(section).findByText("저장 중", { selector: "[role=status]" })
    fireEvent.keyDown(document, { key: "Escape" })
    const history = await within(chatWindow()).findByRole("button", { name: /이전 대화/ })
    // 닫혀 있을 때는 삭제·철회 버튼이 없다(위쪽 줄을 단순하게).
    expect(screen.queryByRole("button", { name: "대화 기록 삭제" })).toBeNull()

    fireEvent.click(history)

    const list = await screen.findByRole("list", { name: "이전 대화" })
    await waitFor(() => expect(within(list).getByText(/저장할 질문/)).toBeTruthy())
    expect(screen.getByRole("button", { name: "대화 기록 삭제" })).toBeTruthy()
    // [이전 대화]에는 철회가 없다. 철회는 플로팅 [저장 설정] 모달 안에만 있다.
    expect(screen.queryByRole("button", { name: /저장 동의 철회/ })).toBeNull()
    expect(within(chatWindow()).queryByRole("button", { name: "저장 설정" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    expect(
      within(await screen.findByRole("region", { name: "AI 대화 저장" })).getByRole("button", {
        name: "저장 동의 철회",
      }),
    ).toBeTruthy()
  }, 15_000)
})
