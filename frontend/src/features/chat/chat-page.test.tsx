// @vitest-environment jsdom
// W-07 화면 테스트(jsdom + Mock): url null 출처 표시, 수동 재시도 3회 상한, 남은 횟수 미상 시 숨김.
// 실제 A08 Backend 연동 결과가 아니다.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import { ChatPage, inputErrorMessage, MAX_MANUAL_RETRIES, Sources } from "./chat-page"
import { useChatSessionStore } from "./chat-store"

const renderChat = () =>
  render(
    <RouterProvider
      router={createMemoryRouter([{ path: "/ai", element: <ChatPage /> }], {
        initialEntries: ["/ai"],
      })}
    />,
  )

beforeEach(() => {
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
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
    renderChat()
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "providerUnavailable" } })
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
    expect(within(notice).getByRole("button", { name: /회원가입/ })).toBeTruthy()
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
