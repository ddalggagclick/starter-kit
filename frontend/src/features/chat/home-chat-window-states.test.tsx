// @vitest-environment jsdom
// 첫 화면 대화창 상태 시험(#225): 남은 횟수 표시, 비로그인 하루 한도, S7 판단 유보, S9 사용 제한 안내 구분.
// chat-page.test.tsx(쓰지 않는 /ai 화면 시험)에만 있던 확인 항목을 실제로 쓰는 첫 화면 대화창 기준으로 옮겼다.
// 확인 내용은 원래 시험과 같다. 실제 라우터(appRoutes) + Mock A08 + 메모리 IndexedDB. 실제 Backend 연동 결과가 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import type { MockAiScenario } from "@/mocks/ai-stream"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { WITHHELD_COPY } from "@/shared/content/chat"
import { inheritanceDb } from "@/shared/storage/db"
import { useChatSessionStore } from "./chat-store"

const STREAM_WAIT = { timeout: 5000 }
const LIMIT_TITLE = "오늘 사용할 수 있는 AI 질문을 모두 사용했습니다."
const STATIC_INFO = /체크리스트와 절차 안내는 그대로 이용할 수 있습니다/

const renderHome = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/ai"] })} />
    </QueryClientProvider>,
  )

const chatWindow = () => screen.getByRole("region", { name: "AI에게 질문하기" })
const conversation = () => screen.getByRole("region", { name: "대화" })
const sendButton = () =>
  within(chatWindow()).getByRole("button", { name: "보내기" }) as HTMLButtonElement
const signInMember = () =>
  act(() =>
    useAuthStore
      .getState()
      .signIn({ accountId: "mock:demo@example.com", email: "demo@example.com" }),
  )

const askWith = (scenario: MockAiScenario, question = "상속포기 기한") => {
  act(() => useMockAiScenarioStore.setState({ scenario }))
  fireEvent.change(within(chatWindow()).getByLabelText("질문"), { target: { value: question } })
  fireEvent.click(sendButton())
}

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  useMockAiScenarioStore.setState({ scenario: "answered" })
})
afterEach(cleanup)

describe("남은 질문 횟수", () => {
  it("남은 횟수를 모르면(null) 숫자를 표시하지 않는다", () => {
    useChatSessionStore.setState({ guestRemaining: null })
    renderHome()
    expect(within(chatWindow()).queryByText(/오늘 남은 질문/)).toBeNull()
  })

  it("남은 횟수를 알면 비로그인 사용자에게 표시한다", () => {
    renderHome()
    expect(within(chatWindow()).getByText(/오늘 남은 질문 10회/)).toBeTruthy()
  })

  it("로그인 사용자에게는 남은 횟수와 하루 한도 안내를 보이지 않는다", () => {
    useChatSessionStore.setState({ guestRemaining: 0 })
    signInMember()
    renderHome()

    expect(within(chatWindow()).queryByText(/오늘 남은 질문/)).toBeNull()
    expect(within(chatWindow()).queryByText(LIMIT_TITLE)).toBeNull()
  })
})

describe("비로그인 하루 한도 (3-7-1)", () => {
  it("남은 횟수가 0이면 질문을 보내기 전에 바로 S9 안내와 로그인 진입을 보이고 보내기를 막는다", () => {
    useChatSessionStore.setState({ guestRemaining: 0 })
    renderHome()

    const title = within(chatWindow()).getByText(LIMIT_TITLE)
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByRole("link", { name: "로그인" })).toBeTruthy()
    expect(within(notice).getByRole("link", { name: "회원가입" }).getAttribute("href")).toBe(
      "/signup",
    )
    expect(sendButton().disabled).toBe(true)
  })

  it("마지막 질문의 답을 받아 남은 횟수가 0이 되는 순간 안내가 나타난다", async () => {
    useChatSessionStore.setState({ guestRemaining: 1 })
    renderHome()
    expect(within(chatWindow()).queryByText(LIMIT_TITLE)).toBeNull()

    askWith("answered", "상속세")

    expect(await within(chatWindow()).findByText(LIMIT_TITLE, undefined, STREAM_WAIT)).toBeTruthy()
    expect(useChatSessionStore.getState().guestRemaining).toBe(0)
    expect(sendButton().disabled).toBe(true)
  }, 10_000)
})

describe("S6·S7·S9 안내 구분 (7-2-2)", () => {
  it("S7 판단 유보는 [다시 시도]를 권하지 않고 공식 확인 경로를 안내한다", async () => {
    renderHome()
    askWith("withheld")

    expect(
      await within(conversation()).findByText(WITHHELD_COPY.message, undefined, STREAM_WAIT),
    ).toBeTruthy()
    // 링크 이름 끝에 화면낭독기용 "(새 창)"이 붙는다.
    const official = within(conversation()).getByRole("link", {
      name: new RegExp(`^${WITHHELD_COPY.link.title}`),
    })
    expect(official.getAttribute("href")).toBe(WITHHELD_COPY.link.url)
    expect(within(conversation()).queryByRole("button", { name: "다시 시도" })).toBeNull()
    expect(within(conversation()).queryByText("일시적인 문제로 답변하지 못했습니다.")).toBeNull()
  }, 10_000)

  it("남은 횟수를 모를 때(실제 A08) 서버 429를 받으면 S9와 로그인·회원가입 진입, 정적 안내 유지를 보인다", async () => {
    useChatSessionStore.setState({ guestRemaining: null })
    renderHome()
    askWith("guestLimit")

    const title = await within(chatWindow()).findByText(LIMIT_TITLE)
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByRole("link", { name: "로그인" })).toBeTruthy()
    expect(within(notice).getByRole("link", { name: "회원가입" })).toBeTruthy()
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
    // 대화 안에는 한 줄만 남기고 같은 안내·버튼을 두 번 보이지 않는다(9번 통합 검증 회귀).
    expect(within(chatWindow()).getAllByText(LIMIT_TITLE)).toHaveLength(1)
    expect(within(chatWindow()).getAllByRole("link", { name: "회원가입" })).toHaveLength(1)
    expect(within(conversation()).getByText(/모두 사용해 답변하지 않았습니다/)).toBeTruthy()
  })

  it("서버가 하루 한도(GUEST_DAILY_LIMIT)를 보내면 로그인 중이어도 하루 한도로 안내한다", async () => {
    signInMember()
    renderHome()
    askWith("guestLimit")

    const title = await within(chatWindow()).findByText(LIMIT_TITLE)
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(/내일 다시 이용해 주세요/)).toBeTruthy()
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
    expect(within(notice).queryByRole("link", { name: "로그인" })).toBeNull()
  })

  it("공급자 제한(S9)도 AI만 멈추고 정적 안내는 계속 쓸 수 있다고 알린다", async () => {
    renderHome()
    askWith("providerRateLimit")

    const title = await within(conversation()).findByText(
      "지금은 AI 질문이 많아 답변하지 못했습니다.",
      undefined,
      STREAM_WAIT,
    )
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
  }, 10_000)
})

describe("로그인 사용자 1분 제한 (3-7-3, MEMBER_MINUTE_LIMIT)", () => {
  it("하루 한도처럼 '내일'을 말하지 않고, 잠시 뒤 다시 질문하도록 [다시 시도]와 정적 안내 유지를 보인다", async () => {
    signInMember()
    renderHome()
    askWith("memberMinuteLimit")

    const notice = (
      await within(conversation()).findByText("짧은 시간에 질문이 많아 잠시 멈췄습니다.")
    ).closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(/1분 정도 지난 뒤 다시 질문해 주세요/)).toBeTruthy()
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
    expect(within(notice).getByRole("button", { name: "다시 시도" })).toBeTruthy()
    expect(within(chatWindow()).queryByText(/내일 다시 이용해 주세요/)).toBeNull()
    expect(within(chatWindow()).queryByText(LIMIT_TITLE)).toBeNull()
  })
})
