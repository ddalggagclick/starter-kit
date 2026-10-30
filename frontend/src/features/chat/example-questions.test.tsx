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

  // #227 사용자 제공 문구: 주제 4개 × 2개 = 8개, 대화창 위에는 주제마다 첫 질문 1개씩(4개).
  it("예시는 주제 4개에 2개씩 8개이고, 대화창 위에는 주제별 첫 질문 4개가 보인다", () => {
    expect(EXAMPLE_QUESTION_GROUPS.map((group) => group.title)).toEqual([
      "절차 · 기한",
      "상속세",
      "채무 · 포기",
      "서류",
    ])
    for (const group of EXAMPLE_QUESTION_GROUPS) expect(group.questions).toHaveLength(2)
    expect(FEATURED_EXAMPLE_QUESTIONS).toEqual(
      EXAMPLE_QUESTION_GROUPS.map((group) => group.questions[0]),
    )
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

  it("대화창 위 예시는 [더보기] 전체 목록에도 들어 있다", () => {
    for (const question of FEATURED_EXAMPLE_QUESTIONS) expect(all).toContain(question)
  })
})

describe("ExampleQuestions 부품", () => {
  it("대화창 위 예시를 '자주 묻는 질문' 묶음으로 보이고, 누르면 그 질문을 넘긴다", () => {
    const onPick = vi.fn()
    render(<ExampleQuestions onPick={onPick} />)

    const group = screen.getByRole("group", { name: "자주 묻는 질문" })
    // 대화창 위 예시 + [더보기](#220). #227: ＋는 아이콘이라 글자는 "더보기"다.
    const buttons = within(group).getAllByRole("button")
    expect(buttons.map((button) => button.textContent)).toEqual([
      ...FEATURED_EXAMPLE_QUESTIONS,
      "더보기",
    ])
    fireEvent.click(within(group).getByRole("button", { name: FEATURED_EXAMPLE_QUESTIONS[1] }))
    expect(onPick).toHaveBeenCalledWith(FEATURED_EXAMPLE_QUESTIONS[1])
  })

  // #227 최신 시안: 예시는 한 줄이고 옆으로 밀어 나머지를 본다. 칩을 숨기지 않아 Tab·화면낭독기로 모두 닿고,
  //   [더보기]는 칩 줄 밖 오른쪽에 있다. (넘칠 때 끝을 흐리게 하는 것은 실제 배치가 필요해 브라우저에서 확인한다.)
  it("한 줄 칩 줄은 줄바꿈 없이 옆으로 밀리고, 모두 닿으며, [더보기]는 줄 밖에 있다", () => {
    render(<ExampleQuestions onPick={vi.fn()} />)
    const group = screen.getByRole("group", { name: "자주 묻는 질문" })
    const row = screen.getByTestId("example-chip-row")
    expect(row.className).toContain("flex-nowrap")
    expect(row.className).toContain("overflow-x-auto")
    expect(
      within(row)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual([...FEATURED_EXAMPLE_QUESTIONS])
    const more = within(group).getByRole("button", { name: "더보기" })
    expect(row.contains(more)).toBe(false)
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
        <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/ai"] })} />
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
