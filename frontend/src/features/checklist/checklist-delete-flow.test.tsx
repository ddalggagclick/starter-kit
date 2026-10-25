// @vitest-environment jsdom
// W-02 삭제·철회 화면 흐름(4-3-1~4-3-3): 실제 라우터 + 메모리 IndexedDB. 실브라우저 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { grantChecklistConsentWithSnapshot, loadConsentStatuses } from "@/shared/storage/consent"
import { GUEST_NAMESPACE, inheritanceDb, loadChecklist } from "@/shared/storage/db"

const ANSWERS: InitialAnswers = {
  relationship: "spouse",
  deathDate: null,
  deathDateUnknown: true,
  oneStopApplication: "no",
}

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
  // 저장에 동의해 둔 사용자가 다시 방문한 상태
  await grantChecklistConsentWithSnapshot(inheritanceDb, GUEST_NAMESPACE, {
    answers: ANSWERS,
    riskAnswers: {},
    procedureStates: useInheritanceStore.getState().procedureStates,
  })
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/checklist"] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  await screen.findByText(/이 기기에 저장한 답변을 불러왔습니다/)
  await screen.findByText(/● 이 기기에 저장 중/)
})
afterEach(cleanup)

describe("W-02 삭제·철회", () => {
  it("[체크리스트 삭제] 뒤 화면이 바뀌어도 완료 안내가 남고, 동의는 유지된다", async () => {
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 삭제" }))
    fireEvent.click(await screen.findByRole("button", { name: "삭제: 체크리스트 기록" }))

    expect(
      await screen.findByText(/체크리스트 기록을 삭제했습니다. 저장 동의는 유지됩니다/),
    ).toBeTruthy()
    expect(screen.getByRole("link", { name: "질문에 답하기" })).toBeTruthy()
    expect(await loadChecklist(inheritanceDb, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
    expect((await loadConsentStatuses(inheritanceDb, GUEST_NAMESPACE)).checklist).toBe("ready")
  })

  it("동의 철회 뒤 기록과 동의가 사라지고 완료 안내가 남는다", async () => {
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 저장 동의 철회" }))
    fireEvent.click(await screen.findByRole("button", { name: "동의 철회: 체크리스트 기록 삭제" }))

    expect(
      await screen.findByText(/저장 동의를 철회하고 이 기기의 체크리스트 기록을 삭제했습니다/),
    ).toBeTruthy()
    await waitFor(async () =>
      expect((await loadConsentStatuses(inheritanceDb, GUEST_NAMESPACE)).checklist).toBe(
        "not-consented",
      ),
    )
    expect(await loadChecklist(inheritanceDb, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
  })
})
