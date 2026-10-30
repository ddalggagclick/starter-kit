// @vitest-environment jsdom
// W-02 삭제·철회 화면 흐름(4-3-1~4-3-3): 실제 라우터 + 메모리 IndexedDB. 실브라우저 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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
  // [체크리스트 삭제]는 목록 아래에 늘 보이고, 기기에 저장된 기록을 불러오면 누를 수 있게 된다.
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "체크리스트 삭제" }) as HTMLButtonElement).disabled,
    ).toBe(false),
  )
})
afterEach(cleanup)

describe("W-02 삭제·철회", () => {
  it("[체크리스트 삭제] 뒤 화면이 바뀌어도 완료 안내가 남고, 동의는 유지된다", async () => {
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 삭제" }))
    // #227 시안 확인창: [취소] [삭제] 순서, [삭제]는 빨간 버튼
    const confirm = await screen.findByRole("dialog", { name: "체크리스트를 삭제할까요?" })
    expect(
      within(confirm)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["취소", "삭제"])
    expect(within(confirm).getByRole("button", { name: "삭제" }).className).toContain(
      "bg-danger-foreground",
    )
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "체크리스트를 삭제할까요?" })).getByRole(
        "button",
        { name: "삭제" },
      ),
    )

    expect(
      await screen.findByText(/체크리스트 기록을 삭제했습니다. 저장 동의는 유지됩니다/),
    ).toBeTruthy()
    expect(screen.getByRole("button", { name: "처음 시작하기" })).toBeTruthy()
    // #227: 삭제 직후에는 질문 모달 없이 빈 화면("먼저 상황을 알려주세요")을 그대로 보인다.
    expect(screen.getByRole("heading", { name: "먼저 상황을 알려주세요" })).toBeTruthy()
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(await loadChecklist(inheritanceDb, GUEST_NAMESPACE)).toEqual({ ok: true, value: null })
    expect((await loadConsentStatuses(inheritanceDb, GUEST_NAMESPACE)).checklist).toBe("ready")
  })

  it("동의 철회 뒤 기록과 동의가 사라지고 완료 안내가 남는다", async () => {
    // 철회는 플로팅 [저장 설정] 창의 "체크리스트 저장" 칸에서 한다.
    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    const device = await screen.findByRole("region", { name: "이 기기 저장" })
    await within(device).findByText("저장 중", { selector: "[role=status]" })
    fireEvent.click(
      within(device).getByRole("button", {
        name: "저장 동의 철회",
      }),
    )
    fireEvent.click(
      within(
        await screen.findByRole("dialog", { name: "체크리스트 저장 동의를 철회할까요?" }),
      ).getByRole("button", { name: "동의 철회" }),
    )

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
