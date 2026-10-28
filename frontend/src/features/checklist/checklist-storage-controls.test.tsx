// @vitest-environment jsdom
// W-02 삭제·철회 결과가 요청한 계정에 고정되는지(리뷰 회귀 P1). 계정이 바뀌면 이전 계정의 결과·재시도를 보이지 않는다.
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import { accountNamespace } from "@/shared/storage/db"
import { useChecklistStorageStore } from "./checklist-storage"
import { ChecklistStorageControls } from "./checklist-storage-controls"

beforeEach(() => useAuthStore.getState().signOut())
afterEach(cleanup)

describe("ChecklistStorageControls", () => {
  it("A 계정에서 실패한 삭제의 안내와 [다시 시도]는 B 계정으로 바뀌면 보이지 않는다", () => {
    useAuthStore.getState().signIn({ accountId: "user-a", email: null })
    useChecklistStorageStore.setState({
      status: "ready",
      lastAction: { namespace: accountNamespace("user-a"), action: "delete", ok: false },
    })
    render(<ChecklistStorageControls />)
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy()

    act(() => useAuthStore.getState().signIn({ accountId: "user-b", email: null }))

    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull()
    expect(screen.queryByText(/삭제하지 못했습니다/)).toBeNull()
  })
})
