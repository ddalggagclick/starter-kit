// @vitest-environment jsdom
// W-07 화면 테스트(jsdom + Mock): url null 출처 표시, 수동 재시도 3회 상한, 남은 횟수 미상 시 숨김.
// 실제 A08 Backend 연동 결과가 아니다.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import type { MockAiScenario } from "@/mocks/ai-stream"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { WITHHELD_COPY } from "@/shared/content/chat"
import {
  ChatPage,
  inputErrorMessage,
  MAX_MANUAL_RETRIES,
  rateLimitKind,
  Sources,
} from "./chat-page"
import { useChatSessionStore } from "./chat-store"

const renderChat = () =>
  render(
    <RouterProvider
      router={createMemoryRouter([{ path: "/ai", element: <ChatPage /> }], {
        initialEntries: ["/ai"],
      })}
    />,
  )

// #205: 화면 드롭다운이 없어져 시험 코드에서 Mock 응답 시나리오를 정한다.
const setScenario = (scenario: MockAiScenario) => useMockAiScenarioStore.setState({ scenario })

beforeEach(() => {
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  setScenario("answered")
})
afterEach(cleanup)

describe("Sources", () => {
  it("url이 있으면 새 탭 링크, url이 null이면 링크 없이 제목만 보인다", () => {
    render(
      <Sources
        sources={[
          { title: "대한법률구조공단 · 전화 상담 132", url: null },
          { title: "법원 전자민원센터", url: "https://help.scourt.go.kr" },
        ]}
      />,
    )

    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute("href")).toBe("https://help.scourt.go.kr")
    expect(links[0].getAttribute("target")).toBe("_blank")
    const phone = screen.getByText("대한법률구조공단 · 전화 상담 132")
    expect(phone.closest("a")).toBeNull()
  })

  it("url이 null인 출처가 여럿이어도 모두 보이고, 2개를 넘으면 추가 출처 보기로 접는다", () => {
    render(
      <Sources
        sources={[
          { title: "전화 상담 A", url: null },
          { title: "전화 상담 B", url: null },
          { title: "전화 상담 C", url: null },
        ]}
      />,
    )

    expect(screen.getByText("전화 상담 A")).toBeTruthy()
    expect(screen.getByText("전화 상담 B")).toBeTruthy()
    expect(screen.queryByText("전화 상담 C")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "추가 출처 보기 (1)" }))
    expect(screen.getByText("전화 상담 C")).toBeTruthy()
    expect(screen.queryAllByRole("link")).toHaveLength(0)
  })
})

describe("W-07 수동 재시도 (Q47)", () => {
  it(`S6에서 같은 질문은 ${MAX_MANUAL_RETRIES}회까지만 다시 시도할 수 있다`, async () => {
    setScenario("providerUnavailable")
    renderChat()
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))

    for (let attempt = 0; attempt < MAX_MANUAL_RETRIES; attempt += 1) {
      fireEvent.click(await screen.findByRole("button", { name: "다시 시도" }))
    }

    expect(await screen.findByText(/다시 시도 횟수\(3회\)를 모두 사용했습니다/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull()
    // 실패한 질문은 대화에 한 번만 남는다(재시도할 때마다 이전 실패를 지운다).
    const conversation = screen.getByRole("region", { name: "대화" })
    expect(within(conversation).getAllByText("상속포기 기한")).toHaveLength(1)
  })
})

describe("W-07 남은 질문 횟수", () => {
  it("남은 횟수를 모르면(null) 숫자를 표시하지 않는다", () => {
    useChatSessionStore.setState({ guestRemaining: null })
    renderChat()
    expect(screen.queryByText(/오늘 남은 질문/)).toBeNull()
  })

  it("남은 횟수를 알면 비로그인 사용자에게 표시한다", () => {
    renderChat()
    expect(screen.getByText(/오늘 남은 질문 10회/)).toBeTruthy()
  })
})

describe("422 입력 오류 문구", () => {
  it("서버 message가 코드 이름뿐이면 코드를 보이지 않고 안내 문구를 쓴다", () => {
    const message = inputErrorMessage({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "VALIDATION_ERROR",
    })
    expect(message).not.toContain("VALIDATION_ERROR")
    expect(message).toContain("200자")
  })

  it("서버가 사람이 읽을 문장을 보내면 그대로 쓴다", () => {
    expect(
      inputErrorMessage({
        status: 422,
        code: "VALIDATION_ERROR",
        message: "질문을 입력해 주세요.",
      }),
    ).toBe("질문을 입력해 주세요.")
  })
})

describe("W-07 비로그인 하루 한도 (3-7-1)", () => {
  it("남은 횟수가 0이면 질문을 보내기 전에 바로 S9 안내와 로그인 진입을 보이고 보내기를 막는다", () => {
    useChatSessionStore.setState({ guestRemaining: 0 })
    renderChat()

    const title = screen.getByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByRole("link", { name: "로그인" })).toBeTruthy()
    expect(within(notice).getByRole("link", { name: "회원가입" }).getAttribute("href")).toBe(
      "/signup",
    )
    expect((screen.getByRole("button", { name: "보내기" }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it("마지막 질문의 답을 받아 남은 횟수가 0이 되는 순간 안내가 나타난다", async () => {
    useChatSessionStore.setState({ guestRemaining: 1 })
    renderChat()
    expect(screen.queryByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")).toBeNull()

    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "상속세" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))

    expect(
      await screen.findByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.", undefined, {
        timeout: 5000,
      }),
    ).toBeTruthy()
    expect(useChatSessionStore.getState().guestRemaining).toBe(0)
  }, 10_000)

  it("로그인 사용자에게는 남은 횟수 안내를 보이지 않는다", () => {
    useChatSessionStore.setState({ guestRemaining: 0 })
    useAuthStore
      .getState()
      .signIn({ accountId: "mock:demo@example.com", email: "demo@example.com" })
    renderChat()

    expect(screen.queryByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")).toBeNull()
  })
})

describe("S6·S7·S9 안내 구분 (7-2-2)", () => {
  const STREAM_WAIT = { timeout: 5000 }
  const LIMIT_TITLE = "오늘 사용할 수 있는 AI 질문을 모두 사용했습니다."
  const STATIC_INFO = /체크리스트와 절차 안내는 그대로 이용할 수 있습니다/

  const askWith = (scenario: MockAiScenario) => {
    act(() => setScenario(scenario))
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))
  }

  it("S6 기술 오류는 질문이 남아 있다고 알리고 [다시 시도]를 준다", async () => {
    renderChat()
    askWith("providerUnavailable")

    expect(await screen.findByText("일시적인 문제로 답변하지 못했습니다.")).toBeTruthy()
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy()
    expect(screen.queryByText(WITHHELD_COPY.message)).toBeNull()
  })

  it("S7 판단 유보는 [다시 시도]를 권하지 않고 공식 확인 경로를 안내한다", async () => {
    renderChat()
    askWith("withheld")

    expect(await screen.findByText(WITHHELD_COPY.message, undefined, STREAM_WAIT)).toBeTruthy()
    // 링크 이름 끝에 화면낭독기용 "(새 창)"이 붙는다.
    const official = screen.getByRole("link", { name: new RegExp(`^${WITHHELD_COPY.link.title}`) })
    expect(official.getAttribute("href")).toBe(WITHHELD_COPY.link.url)
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull()
    expect(screen.queryByText("일시적인 문제로 답변하지 못했습니다.")).toBeNull()
  }, 10_000)

  it("남은 횟수를 모를 때(실제 A08) 서버 429를 받으면 S9와 로그인·회원가입 진입, 정적 안내 유지를 보인다", async () => {
    useChatSessionStore.setState({ guestRemaining: null })
    renderChat()
    askWith("guestLimit")

    const notice = (await screen.findByText(LIMIT_TITLE)).closest("[role=status]") as HTMLElement
    expect(within(notice).getByRole("link", { name: "로그인" })).toBeTruthy()
    expect(within(notice).getByRole("link", { name: "회원가입" })).toBeTruthy()
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
    // 대화 안에는 한 줄만 남기고 같은 안내·버튼을 두 번 보이지 않는다(9번 통합 검증 회귀).
    expect(screen.getAllByText(LIMIT_TITLE)).toHaveLength(1)
    expect(screen.getAllByRole("link", { name: "회원가입" })).toHaveLength(1)
    const conversation = screen.getByRole("region", { name: "대화" })
    expect(within(conversation).getByText(/모두 사용해 답변하지 않았습니다/)).toBeTruthy()
  })

  it("서버가 하루 한도(GUEST_DAILY_LIMIT)를 보내면 로그인 중이어도 하루 한도로 안내한다", async () => {
    useAuthStore
      .getState()
      .signIn({ accountId: "mock:demo@example.com", email: "demo@example.com" })
    renderChat()
    askWith("guestLimit")

    const notice = (await screen.findByText(LIMIT_TITLE)).closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(/내일 다시 이용해 주세요/)).toBeTruthy()
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
    expect(within(notice).queryByRole("link", { name: "로그인" })).toBeNull()
  })

  it("공급자 제한(S9)도 AI만 멈추고 정적 안내는 계속 쓸 수 있다고 알린다", async () => {
    renderChat()
    askWith("providerRateLimit")

    const title = await screen.findByText(
      "지금은 AI 질문이 많아 답변하지 못했습니다.",
      undefined,
      STREAM_WAIT,
    )
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(STATIC_INFO)).toBeTruthy()
  }, 10_000)
})

describe("로그인 사용자 1분 제한 (3-7-3, MEMBER_MINUTE_LIMIT)", () => {
  const MINUTE_TITLE = "짧은 시간에 질문이 많아 잠시 멈췄습니다."

  it("하루 한도처럼 '내일'을 말하지 않고, 잠시 뒤 다시 질문하도록 [다시 시도]와 정적 안내 유지를 보인다", async () => {
    useAuthStore
      .getState()
      .signIn({ accountId: "mock:demo@example.com", email: "demo@example.com" })
    setScenario("memberMinuteLimit")
    renderChat()
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))

    const notice = (await screen.findByText(MINUTE_TITLE)).closest("[role=status]") as HTMLElement
    expect(within(notice).getByText(/1분 정도 지난 뒤 다시 질문해 주세요/)).toBeTruthy()
    expect(
      within(notice).getByText(/체크리스트와 절차 안내는 그대로 이용할 수 있습니다/),
    ).toBeTruthy()
    expect(within(notice).getByRole("button", { name: "다시 시도" })).toBeTruthy()
    expect(screen.queryByText(/내일 다시 이용해 주세요/)).toBeNull()
    expect(screen.queryByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")).toBeNull()
  })

  it("제한 사유는 message로 정하고, 사유가 없으면 로그인 여부로 정한다", () => {
    const failure = (message: string | null) => ({ status: 429, code: "RATE_LIMITED", message })
    expect(rateLimitKind(failure("MEMBER_MINUTE_LIMIT"), false)).toBe("memberMinute")
    // 화면의 로그인 상태와 서버 판단이 다르면 서버가 보낸 사유를 따른다.
    expect(rateLimitKind(failure("MEMBER_MINUTE_LIMIT"), true)).toBe("memberMinute")
    expect(rateLimitKind(failure("GUEST_DAILY_LIMIT"), false)).toBe("guestDaily")
    expect(rateLimitKind(failure("GUEST_DAILY_LIMIT"), true)).toBe("guestDaily")
    // 사유를 보내지 않는 서버(message가 코드 이름뿐이거나 없음)
    expect(rateLimitKind(failure("RATE_LIMITED"), true)).toBe("guestDaily")
    expect(rateLimitKind(failure(null), false)).toBe("memberMinute")
  })
})
