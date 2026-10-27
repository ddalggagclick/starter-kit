// @vitest-environment jsdom
// 7-2-2 핸드오프 오류 안내(D-08): 만료·재사용·없는 토큰은 같은 실패 안내와 이어 갈 길을 보인다.
// 실제 라우터 + Mock A05 + 메모리 IndexedDB. 실제 카카오·Backend 연동 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { resetMockApiState } from "@/mocks/mock-api"
import { HANDOFF_FAILURE_COPY } from "@/shared/content/checklist"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { grantChecklistConsentWithSnapshot } from "@/shared/storage/consent"
import { GUEST_NAMESPACE, inheritanceDb } from "@/shared/storage/db"

const WAIT = { timeout: 3000 }

const renderAt = (path: string) => {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
})
afterEach(cleanup)

describe("핸드오프 실패 안내 (7-2-2)", () => {
  it("토큰을 주소에서 지우고, 실패하면 실패 안내와 처음부터 답하기를 보인다", async () => {
    const router = renderAt("/checklist?handoff=expired-token")

    expect(await screen.findByText(HANDOFF_FAILURE_COPY, undefined, WAIT)).toBeTruthy()
    expect(router.state.location.search).not.toContain("handoff")
    expect(screen.getByRole("link", { name: "질문 3개에 처음부터 답하기" })).toBeTruthy()
  })

  it("이 기기에 이전 답변이 있으면 그 답변으로 이어 볼 수 있다", async () => {
    const answers: InitialAnswers = {
      relationship: "spouse",
      deathDate: null,
      deathDateUnknown: true,
      oneStopApplication: "no",
    }
    await grantChecklistConsentWithSnapshot(inheritanceDb, GUEST_NAMESPACE, {
      answers,
      riskAnswers: {},
      procedureStates: useInheritanceStore.getState().procedureStates,
    })
    renderAt("/checklist?handoff=expired-token")

    fireEvent.click(
      await screen.findByRole("button", { name: "이 기기의 이전 답변으로 이어 보기" }, WAIT),
    )

    expect(screen.getByText("지금 확인할 공통 절차")).toBeTruthy()
    expect(screen.queryByText(HANDOFF_FAILURE_COPY)).toBeNull()
  })
})
