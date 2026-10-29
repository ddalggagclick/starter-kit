// @vitest-environment jsdom
// [+ 더보기] 전체 예시 모달 시험(#220): 모달 부품, 첫 화면에서 열고 고르기·닫기·초점.
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
import { useChatSessionStore } from "./chat-store"
import { ExampleQuestionsModal } from "./example-questions-modal"

afterEach(cleanup)

// 모달에서만 볼 수 있는 예시(대화창 위 칩 줄에 없는 것)
const MODAL_ONLY = EXAMPLE_QUESTION_GROUPS.flatMap((group) => group.questions).find(
  (question) => !FEATURED_EXAMPLE_QUESTIONS.includes(question),
) as string

describe("ExampleQuestionsModal 부품", () => {
  it("주제별 묶음을 모두 보이고, 질문을 누르면 넘기며, [닫기]는 닫기를 부른다", () => {
    const onPick = vi.fn()
    const onClose = vi.fn()
    render(
      <ExampleQuestionsModal groups={EXAMPLE_QUESTION_GROUPS} onPick={onPick} onClose={onClose} />,
    )

    const dialog = screen.getByRole("dialog", { name: "자주 묻는 질문" })
    for (const group of EXAMPLE_QUESTION_GROUPS) {
      const section = within(dialog).getByRole("group", { name: group.title })
      expect(within(section).getAllByRole("button")).toHaveLength(group.questions.length)
    }
    fireEvent.click(within(dialog).getByRole("button", { name: MODAL_ONLY }))
    expect(onPick).toHaveBeenCalledWith(MODAL_ONLY)

    fireEvent.click(within(dialog).getByRole("button", { name: "닫기" }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe("첫 화면 [+ 더보기] (#220)", () => {
  beforeEach(() => {
    useAuthStore.getState().signOut()
    useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/"] })} />
      </QueryClientProvider>,
    )
  })

  const openMore = () => {
    const more = screen.getByRole("button", { name: "더보기" })
    more.focus()
    fireEvent.click(more)
    return more
  }

  it("모달에서 고른 질문은 질문창에 담기고, 모달이 닫히며 초점은 질문창으로 가고, 보내지는 않는다", () => {
    openMore()
    const dialog = screen.getByRole("dialog", { name: "자주 묻는 질문" })

    fireEvent.click(within(dialog).getByRole("button", { name: MODAL_ONLY }))

    expect(screen.queryByRole("dialog")).toBeNull()
    const input = screen.getByLabelText("질문") as HTMLTextAreaElement
    expect(input.value).toBe(MODAL_ONLY)
    expect(document.activeElement).toBe(input)
    expect(screen.queryByText(/질문을 보내는 중|공식 자료 검색 중/)).toBeNull()
  })

  it("Esc로 닫으면 아무것도 담지 않고 초점은 [더보기]로 돌아온다", () => {
    const more = openMore()
    expect(screen.getByRole("dialog")).toBeTruthy()

    fireEvent.keyDown(document, { key: "Escape" })

    expect(screen.queryByRole("dialog")).toBeNull()
    expect((screen.getByLabelText("질문") as HTMLTextAreaElement).value).toBe("")
    expect(document.activeElement).toBe(more)
  })
})
