// @vitest-environment jsdom
// 자주 묻는 예시 질문 시험(#214): 문구 규칙, 칩 부품, 첫 화면에서 누르면 질문창에 담기기만 하는지.
// 실제 A08 Backend 연동 결과가 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import {
  EXAMPLE_QUESTION_GROUPS,
  FEATURED_EXAMPLE_QUESTIONS,
} from "@/shared/content/example-questions"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { useChatSessionStore } from "./chat-store"
import { ExampleQuestions } from "./example-questions"

afterEach(cleanup)

describe("예시 질문 문구 규칙", () => {
  const all = EXAMPLE_QUESTION_GROUPS.flatMap((group) => group.questions)

  it("대화창 위 예시는 5개다", () => {
    expect(FEATURED_EXAMPLE_QUESTIONS).toHaveLength(5)
  })

  it("모든 예시는 AI 입력 한도(200자) 안이고 같은 질문이 두 번 없다", () => {
    for (const question of [...FEATURED_EXAMPLE_QUESTIONS, ...all]) {
      expect(question.trim()).not.toBe("")
      expect(countUnicodeCodePoints(question)).toBeLessThanOrEqual(
        CHAT_INPUT_POLICY.maxQuestionCodePoints,
      )
    }
    expect(new Set(all).size).toBe(all.length)
    expect(new Set(FEATURED_EXAMPLE_QUESTIONS).size).toBe(FEATURED_EXAMPLE_QUESTIONS.length)
  })

  it("대화창 위 5개는 [+더보기] 전체 목록에도 들어 있다", () => {
    for (const question of FEATURED_EXAMPLE_QUESTIONS) expect(all).toContain(question)
  })
})

describe("ExampleQuestions 부품", () => {
  it("5개를 '자주 묻는 질문' 묶음으로 보이고, 누르면 그 질문을 넘긴다", () => {
    const onPick = vi.fn()
    render(<ExampleQuestions onPick={onPick} />)

    const group = screen.getByRole("group", { name: "자주 묻는 질문" })
    // 예시 5개 + [+ 더보기](#220)
    const buttons = within(group).getAllByRole("button")
    expect(buttons.map((button) => button.textContent)).toEqual([
      ...FEATURED_EXAMPLE_QUESTIONS,
      "+ 더보기",
    ])
    fireEvent.click(within(group).getByRole("button", { name: FEATURED_EXAMPLE_QUESTIONS[1] }))
    expect(onPick).toHaveBeenCalledWith(FEATURED_EXAMPLE_QUESTIONS[1])
  })
})

describe("첫 화면 예시 질문 (#214)", () => {
  beforeEach(() => {
    useAuthStore.getState().signOut()
    useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  })

  it("대화창 위 예시를 누르면 질문창에 담기고 초점이 옮겨지며, 보내지는 않는다", () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/"] })} />
      </QueryClientProvider>,
    )

    const group = screen.getByRole("group", { name: "자주 묻는 질문" })
    fireEvent.click(within(group).getByRole("button", { name: FEATURED_EXAMPLE_QUESTIONS[0] }))

    const input = screen.getByLabelText("질문") as HTMLTextAreaElement
    expect(input.value).toBe(FEATURED_EXAMPLE_QUESTIONS[0])
    expect(document.activeElement).toBe(input)
    expect(screen.queryByText(/질문을 보내는 중|공식 자료 검색 중/)).toBeNull()
    // 보내기를 시도하지도 않는다(시도하면 입력칸 오류나 진행 표시가 생긴다).
    expect(
      within(screen.getByRole("region", { name: "AI에게 질문하기" })).queryByRole("alert"),
    ).toBeNull()
    expect(screen.getByText("궁금한 것을 물어보세요.")).toBeTruthy()
  })
})
