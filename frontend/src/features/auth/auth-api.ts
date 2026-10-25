/*
 * 담당: [A] | 책임: 로그인·로그아웃·세션 복구 호출(Mock / 실제 Backend 전환).
 * PRD: E5 / 태스크 5-2-1, 5-3-1, 5-3-3, 4-2-2.
 * 계약: A13 POST /api/auth/login → {accessToken, expiresIn}, A14 POST /api/auth/refresh → {accessToken},
 *   A14 POST /api/auth/logout → 204 (x-confirmed: true, 경로 제안).
 * 구현: VITE_USE_MOCK_API=false면 공통 Axios(CSRF·401 Refresh 적용)로 호출하고 Access Token을 메모리 세션에 둔다.
 *   계정 ID는 Access Token의 sub에서 읽는다. Mock은 Mock 토큰을 실제 세션에 넣지 않고 이메일로 계정을 구분한다.
 * 제한사항: Refresh 토큰은 HttpOnly 쿠키라 JavaScript에서 다루지 않는다. 비밀번호를 저장하지 않는다.
 */
import { login as loginMock, logout as logoutMock } from "@/mocks/mock-api"
import { AUTH_WIRE, accessSession, accountIdFromAccessToken } from "@/shared/api/auth"
import { loadApiClient, USE_MOCK_API } from "@/shared/api/data-source"

export type SignedInAccount = { accountId: string; email: string | null }

// 실제 응답에 sub가 없으면 계정별 저장 영역을 나눌 수 없어 로그인 실패로 처리한다(다른 계정과 섞이지 않게).
const accountFromToken = (token: string, email: string | null): SignedInAccount => {
  const accountId = accountIdFromAccessToken(token)
  if (!accountId) throw new Error("Access token has no subject")
  return { accountId, email }
}

export const loginRequest = async (email: string, password: string): Promise<SignedInAccount> => {
  if (USE_MOCK_API) {
    await loginMock(email, password)
    return { accountId: `mock:${email}`, email }
  }
  const api = await loadApiClient()
  const response = await api.post<{ accessToken?: string }>("/api/auth/login", { email, password })
  const token = AUTH_WIRE.readAccessToken(response)
  const account = accountFromToken(token, email)
  accessSession.set(token)
  return account
}

// 서버 로그아웃이 실패해도(네트워크 등) 이 탭의 인증 상태는 해제한다. 호출자는 결과와 관계없이 화면을 로그아웃으로 바꾼다.
export const logoutRequest = async (): Promise<void> => {
  try {
    if (USE_MOCK_API) {
      await logoutMock()
      return
    }
    const api = await loadApiClient()
    await api.post("/api/auth/logout")
  } catch {
    // 서버 세션 정리 실패는 화면 인증 해제를 막지 않는다.
  } finally {
    accessSession.clear()
  }
}

// 새로고침하면 메모리 Access Token이 사라진다. Refresh 쿠키가 있으면 조용히 다시 받는다(5-3).
// 이메일은 응답에 없어(A21 /api/me 미확정) null이다. 실패하면 비로그인으로 둔다.
export const restoreSessionRequest = async (): Promise<SignedInAccount | null> => {
  if (USE_MOCK_API) return null
  try {
    const api = await loadApiClient()
    const response = await api.post<{ accessToken?: string }>(AUTH_WIRE.refreshPath)
    const token = AUTH_WIRE.readAccessToken(response)
    const account = accountFromToken(token, null)
    accessSession.set(token)
    return account
  } catch {
    accessSession.clear()
    return null
  }
}
