// 로그인·로그아웃 순서 경합 테스트(Mock 모드): 늦게 끝난 로그아웃·로그인이 새 상태를 덮지 않는다.
// 실제 Backend 호출이 아니다.
import { afterEach, describe, expect, it } from "vitest"
import { MOCK_ACCOUNT } from "@/mocks/mock-api"
import { accessSession, StaleSessionError } from "@/shared/api/auth"
import { loginRequest, logoutRequest } from "./auth-api"

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
