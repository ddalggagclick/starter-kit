// 로그인·로그아웃 순서 경합 테스트(Mock 모드): 늦게 끝난 로그아웃·로그인이 새 상태를 덮지 않는다.
// 실제 Backend 호출이 아니다.
import { afterEach, describe, expect, it, vi } from "vitest"
import { MOCK_ACCOUNT, MOCK_LATENCY_MS, resetMockApiState } from "@/mocks/mock-api"
import { accessSession, StaleSessionError } from "@/shared/api/auth"
import { deleteAccountRequest, loginRequest, logoutRequest } from "./auth-api"

afterEach(() => accessSession.clear())

describe("auth-api 세션 순서 (리뷰 회귀)", () => {
  it("로그아웃 응답이 오기 전에 다시 로그인해도 새 토큰이 지워지지 않는다", async () => {
    accessSession.set("a-token")
    const logout = logoutRequest()
    // 로그아웃은 응답을 기다리지 않고 즉시 토큰을 지운다.
    expect(accessSession.get()).toBeNull()

    const epoch = accessSession.begin()
    accessSession.setIfCurrent("b-token", epoch)
    await logout

    expect(accessSession.get()).toBe("b-token")
  })

  it("로그인 응답이 오기 전에 로그아웃하면 늦게 온 로그인 응답은 버린다", async () => {
    const login = loginRequest(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password).catch((error) => error)
    await logoutRequest()

    expect(await login).toBeInstanceOf(StaleSessionError)
  })
})

describe("탈퇴 응답과 로그인의 Refresh 쿠키 경합 (리뷰 회귀)", () => {
  afterEach(() => {
    vi.useRealTimers()
    resetMockApiState()
  })

  it("같은 탭에서 탈퇴 요청이 끝나기 전에는 로그인 요청을 보내지 않는다", async () => {
    vi.useFakeTimers()
    resetMockApiState()
    let loginSettled = false

    const deletion = deleteAccountRequest(MOCK_ACCOUNT.password).catch(() => undefined)
    void loginRequest("b@example.com", "bpass1234")
      .catch(() => undefined)
      .finally(() => {
        loginSettled = true
      })

    // 탈퇴 응답 시점: 로그인이 동시에 나갔다면 이때 함께 끝났을 것이다.
    await vi.advanceTimersByTimeAsync(MOCK_LATENCY_MS)
    await deletion
    expect(loginSettled).toBe(false)

    // 탈퇴 응답 뒤에 로그인 요청이 나가 그만큼 뒤에 끝난다.
    await vi.advanceTimersByTimeAsync(MOCK_LATENCY_MS)
    expect(loginSettled).toBe(true)
  })
})
