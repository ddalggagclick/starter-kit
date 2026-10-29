// @vitest-environment jsdom
// 첫 화면 AI 대화창 화면 시험(#210): 실제 라우터(appRoutes) + Mock A08 + 메모리 IndexedDB.
// 실제 브라우저·Backend 검증이 아니다. Mock 답변은 이벤트마다 지연이 있어 몇 초씩 걸린다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { resetMockApiState } from "@/mocks/mock-api"
import { PRIVACY_WARNING } from "@/shared/content/chat"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { inheritanceDb } from "@/shared/storage/db"
import { EXTERNAL_TRANSFER_NOTICE, MAX_MANUAL_RETRIES } from "./chat-parts"
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
  it("배너 아래에 AI 대화창이 있고, 안내 카드는 없다", async () => {
    renderHome()

    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy()
    const window = await screen.findByRole("region", { name: "AI에게 질문하기" })
    expect(within(window).getByRole("heading", { level: 2, name: "AI에게 질문하기" })).toBeTruthy()
    expect(within(window).getByText("궁금한 것을 물어보세요.")).toBeTruthy()
    // 예전 주소 /ai가 찾아올 위치
    expect(window.closest("#ai")).toBeTruthy()

    expect(screen.queryByText("AI에게 질문하기", { selector: "[data-slot=card-title]" })).toBeNull()
    expect(screen.queryByText("공식 근거와 함께 답합니다.")).toBeNull()
    // #227: 대화창 아래 카드 3개(공통 절차·상속 관계·상속세)는 사용자 요청으로 뺐다. 같은 안내는 사이드바 메뉴 모달로 연다.
    expect(screen.queryByRole("region", { name: "안내 바로가기" })).toBeNull()
    expect(screen.queryByText("공통 절차 보기")).toBeNull()
    expect(screen.queryByText("상속 관계 보기")).toBeNull()
    expect(screen.queryByText("상속세 안내")).toBeNull()
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    for (const name of ["전체 절차", "상속 관계", "상속세"]) {
      expect(within(nav).getByRole("button", { name })).toBeTruthy()
    }
  })

  // #227 최신 시안: 제목은 두 줄, [상속 절차 시작하기]는 질문 3개를 지금 화면 위 모달로 연다(첫 화면 대화는 그대로).
  it("배너 제목은 두 줄이고 [상속 절차 시작하기]는 질문 3개 모달을 연다", () => {
    const router = renderHome()
    const title = screen.getAllByRole("heading", { level: 1 })[0]
    expect(title.querySelector("br")).toBeTruthy()
    expect(title.textContent).toBe("무엇부터 해야 할지함께 확인하세요.")
    fireEvent.click(screen.getByRole("button", { name: "상속 절차 시작하기" }))
    const dialog = screen.getByRole("dialog", { name: "상속 절차 시작" })
    expect(within(dialog).getByRole("heading", { name: "먼저 세 가지만 여쭤볼게요" })).toBeTruthy()
    expect(router.state.location.pathname).toBe("/")
    // 사용자 요청으로 뺀 문구(로그인 없이 시작하는 동작은 그대로다).
    expect(screen.queryByText("로그인하지 않아도 바로 시작할 수 있습니다.")).toBeNull()
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

  it("저장 상태는 '저장 안 됨'(점선)에서 동의하면 '저장 중'(초록)으로 바뀐다", async () => {
    renderHome()
    const window = chatWindow()
    const off = await within(window).findByText("저장 안 됨", { selector: "[role=status]" })
    expect(off.className).toContain("border-dashed")
    // 화면낭독기에는 무엇의 상태인지 함께 읽힌다.
    expect(off.textContent).toBe("AI 대화 저장 안 됨")

    fireEvent.click(within(window).getByRole("button", { name: "저장 설정" }))
    fireEvent.click(screen.getByLabelText("AI 대화 저장 정책을 확인했습니다"))
    fireEvent.click(screen.getByRole("button", { name: "저장" }))

    const on = await within(window).findByText("저장 중", { selector: "[role=status]" })
    // #227: 저장 중 표시는 저장 설정을 여는 버튼이다(초록).
    expect(on.closest("button")?.className).toContain("bg-success")
    expect(on.textContent).toBe("AI 대화 저장 중")
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
    // #227: [이전 대화]에는 철회가 없고, "✓ 저장 중"을 누르면 저장 설정(철회) 모달이 열린다. [저장 설정] 버튼은 숨는다.
    expect(screen.queryByRole("button", { name: /저장 동의 철회/ })).toBeNull()
    expect(within(chatWindow()).queryByRole("button", { name: "저장 설정" })).toBeNull()
    fireEvent.click(within(chatWindow()).getByRole("button", { name: /AI 대화 저장 중/ }))
    expect(
      within(screen.getByRole("dialog", { name: "AI 대화 저장" })).getByRole("button", {
        name: "저장 동의 철회",
      }),
    ).toBeTruthy()
  }, 15_000)
})
