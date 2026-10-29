// @vitest-environment jsdom
// 3-7-1 통합 검증: 비로그인 하루 한도(S9)에 도달해도 체크리스트와 절차 안내의 공식 링크는 계속 쓸 수 있다.
// 실제 라우터 + Mock A07 + 메모리 IndexedDB. 실브라우저·실제 Backend 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { useChatSessionStore } from "./chat-store"

beforeEach(() => {
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 0 })
})
afterEach(cleanup)

describe("비로그인 하루 한도 뒤 정적 기능 (3-7-1)", () => {
  it("S9 안내 뒤에도 체크리스트와 절차 안내의 공식 링크를 그대로 쓸 수 있다", async () => {
    const router = createMemoryRouter(appRoutes, { initialEntries: ["/ai"] })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    expect(screen.getByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")).toBeTruthy()

    await act(() => router.navigate("/checklist"))
    expect(screen.getByRole("button", { name: "처음 시작하기" })).toBeTruthy()

    await act(() => router.navigate("/procedures/p01"))
    const official = await screen.findByRole("region", { name: "공식 출처" }, { timeout: 5000 })
    expect(within(official).getAllByRole("link").length).toBeGreaterThan(0)
  }, 10_000)
})
