// @vitest-environment jsdom
// 사이드바 계정 칸 시험(계정 관리 UI 개선 지시서): 로그인 전 [로그인]만, 로그인 후 "로그인 중"·[로그아웃]·[회원 탈퇴].
// 실제 라우터(appRoutes) + Mock. 실제 Backend 검증이 아니다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"

const renderAt = (path: string) =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  )
const sidebar = () => screen.getByRole("complementary", { name: "사이드바" })

beforeEach(() => useAuthStore.getState().signOut())
afterEach(cleanup)

describe("사이드바 계정 칸", () => {
  it("로그인 전에는 [로그인]만 있고 계정 관리 메뉴는 없다", () => {
    renderAt("/guide/tax")
    expect(within(sidebar()).getByRole("button", { name: "로그인" })).toBeTruthy()
    expect(within(sidebar()).queryByText("로그인 중")).toBeNull()
    expect(within(sidebar()).queryByRole("button", { name: /로그아웃/ })).toBeNull()
    expect(within(sidebar()).queryByRole("button", { name: /회원 탈퇴/ })).toBeNull()
  })

  // 사용자 지시: 웹(사이드바)에서는 "로그인 중"·메일을 생략한다(모바일 메뉴에서만 보인다).
  it("로그인 후 웹 사이드바에는 [로그아웃]·[회원 탈퇴]만 있고, 탈퇴는 기존 확인 창을 연다", () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAt("/guide/tax")
    expect(within(sidebar()).queryByText("로그인 중")).toBeNull()
    expect(within(sidebar()).queryByText("a@example.com")).toBeNull()
    expect(within(sidebar()).getByRole("button", { name: /로그아웃/ })).toBeTruthy()
    expect(within(sidebar()).queryByRole("button", { name: "로그인" })).toBeNull()
    fireEvent.click(within(sidebar()).getByRole("button", { name: /회원 탈퇴/ }))
    expect(screen.getByRole("dialog", { name: "회원 탈퇴" })).toBeTruthy()
    // 확인 전에는 로그인 상태 그대로다(탈퇴 실행 없음).
    expect(useAuthStore.getState().accountId).toBe("user-a")
  })

  it("[로그아웃]을 누르면 로그아웃되고 [로그인]으로 돌아간다", () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAt("/guide/tax")
    fireEvent.click(within(sidebar()).getByRole("button", { name: /로그아웃/ }))
    expect(useAuthStore.getState().accountId).toBeNull()
    expect(within(sidebar()).getByRole("button", { name: "로그인" })).toBeTruthy()
  })

  it("사이드바를 접어도 로그아웃·회원 탈퇴에 접근할 수 있다", () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAt("/guide/tax")
    fireEvent.click(within(sidebar()).getByRole("button", { name: "사이드바 접기" }))
    expect(within(sidebar()).getByRole("button", { name: /로그아웃/ })).toBeTruthy()
    expect(within(sidebar()).getByRole("button", { name: "회원 탈퇴" })).toBeTruthy()
  })

  it("모바일 메뉴에서는 '로그인 중'과 메일을 보이고 [로그아웃]·[회원 탈퇴]를 가운데 정렬로 둔다", () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAt("/guide/tax")
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }))
    const drawer = screen.getByRole("dialog", { name: "메뉴" })
    expect(within(drawer).getByRole("status").textContent).toContain("로그인 중")
    expect(within(drawer).getByText("a@example.com")).toBeTruthy()
    const withdraw = within(drawer).getByRole("button", { name: /회원 탈퇴/ })
    expect(withdraw.parentElement?.className).toContain("justify-center")
  })
})
