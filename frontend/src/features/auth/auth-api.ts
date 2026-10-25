/*
 * 담당: [A] | 책임: 로그인·로그아웃·세션 복구 호출(Mock / 실제 Backend 전환).
 * PRD: E5 / 태스크 5-2-1, 5-3-1, 5-3-3, 4-2-2, 5-1-1, 5-5-1, 5-5-3, 5-4-1.
 * 계약: A13 POST /api/auth/login → {accessToken, expiresIn}, A14 POST /api/auth/refresh → {accessToken},
 *   A14 POST /api/auth/logout → 204 (x-confirmed: true, 경로 제안).
 * 구현: VITE_USE_MOCK_API=false면 공통 Axios(CSRF·401 Refresh 적용)로 호출하고 Access Token을 메모리 세션에 둔다.
 *   계정 ID는 Access Token의 sub에서 읽는다. Mock은 Mock 토큰을 실제 세션에 넣지 않고 이메일로 계정을 구분한다.
 * 제한사항: Refresh 토큰은 HttpOnly 쿠키라 JavaScript에서 다루지 않는다. 비밀번호를 저장하지 않는다.
 */
import {
  deleteAccount as deleteAccountMock,
  login as loginMock,
  logout as logoutMock,
  requestPasswordReset as requestPasswordResetMock,
  resendVerificationEmail as resendVerificationMock,
  resetPassword as resetPasswordMock,
  signup as signupMock,
  verifyEmail as verifyEmailMock,
} from "@/mocks/mock-api"
import {
  AUTH_WIRE,
  accessSession,
  accountIdFromAccessToken,
  refreshAccessToken,
  StaleSessionError,
} from "@/shared/api/auth"
import { loadApiClient, USE_MOCK_API } from "@/shared/api/data-source"

export type SignedInAccount = { accountId: string; email: string | null }

// 실제 응답에 sub가 없으면 계정별 저장 영역을 나눌 수 없어 로그인 실패로 처리한다(다른 계정과 섞이지 않게).
const accountFromToken = (token: string, email: string | null): SignedInAccount => {
  const accountId = accountIdFromAccessToken(token)
  if (!accountId) throw new Error("Access token has no subject")
  return { accountId, email }
}

// 같은 탭에서 로그인과 탈퇴가 겹치지 않게 한다.
// - 탈퇴 중 로그인: 탈퇴 응답(Refresh 쿠키 삭제 Set-Cookie)보다 로그인 응답(새 쿠키)이 먼저 오면 새 계정 쿠키가 지워진다.
//   → 로그인은 진행 중인 탈퇴가 끝난 뒤에 요청을 보낸다.
// - 로그인 중 탈퇴: 로그인이 탈퇴 도중 끝나면 탈퇴 요청이 새 계정의 토큰을 달고 나갈 수 있다.
//   → 로그인이 처리 중이면 탈퇴를 시작하지 않는다(AuthOperationConflictError).
// 다른 탭에서 동시에 로그인하는 경우는 프런트엔드만으로 막을 수 없다(API 담당자 조율 필요).
let accountDeletionInFlight: Promise<void> | null = null
let loginsInFlight = 0

export class AuthOperationConflictError extends Error {
  constructor() {
    super("login in progress")
    this.name = "AuthOperationConflictError"
  }
}

const afterAccountDeletion = async () => {
  if (accountDeletionInFlight) await accountDeletionInFlight
}

// 로그인을 시작하면 새 세션 번호를 받는다. 그 사이 끝난 이전 세션의 복구·Refresh 결과는 버려지고,
// 이 로그인 응답도 그 뒤 또 다른 로그인·로그아웃이 있었다면 버린다(StaleSessionError).
export const loginRequest = async (email: string, password: string): Promise<SignedInAccount> => {
  const epoch = accessSession.begin()
  loginsInFlight += 1
  try {
    await afterAccountDeletion()
    return await sendLogin(email, password, epoch)
  } finally {
    loginsInFlight -= 1
  }
}

const sendLogin = async (
  email: string,
  password: string,
  epoch: number,
): Promise<SignedInAccount> => {
  if (USE_MOCK_API) {
    await loginMock(email, password)
    if (!accessSession.isCurrent(epoch)) throw new StaleSessionError()
    return { accountId: `mock:${email}`, email }
  }
  const api = await loadApiClient()
  const response = await api.post<{ accessToken?: string }>("/api/auth/login", { email, password })
  const token = AUTH_WIRE.readAccessToken(response)
  const account = accountFromToken(token, email)
  if (!accessSession.setIfCurrent(token, epoch)) throw new StaleSessionError()
  return account
}

// 이 탭의 토큰은 서버 응답을 기다리지 않고 즉시 지운다. 응답 뒤에 지우면 그 사이 한 재로그인 토큰까지 지워진다.
// 서버 로그아웃이 실패해도(네트워크 등) 화면 인증 해제는 막지 않는다.
export const logoutRequest = async (): Promise<void> => {
  accessSession.end()
  try {
    if (USE_MOCK_API) {
      await logoutMock()
      return
    }
    const api = await loadApiClient()
    await api.post("/api/auth/logout")
  } catch {
    // 서버 세션 정리 실패는 무시한다.
  }
}

// 새로고침하면 메모리 Access Token이 사라진다. Refresh 쿠키가 있으면 조용히 다시 받는다(5-3).
// 401 재시도와 같은 Refresh 실행을 함께 써서 Refresh를 동시에 두 번 보내지 않는다.
// 복구 중에 사용자가 직접 로그인·로그아웃했으면 결과를 버린다. 이메일은 응답에 없어(A21 미확정) null이다.
export const restoreSessionRequest = async (): Promise<SignedInAccount | null> => {
  if (USE_MOCK_API) return null
  const epoch = accessSession.current()
  try {
    await loadApiClient()
    const token = await refreshAccessToken()
    if (!accessSession.isCurrent(epoch)) return null
    return accountFromToken(token, null)
  } catch {
    // sub가 없는 토큰을 받았다면 이 세션에 남기지 않는다.
    if (accessSession.isCurrent(epoch)) accessSession.clear()
    return null
  }
}

// ── A11·A12·A15·A16 계정 관리 (x-confirmed: true, 경로 제안) ──────────────────

export const signupRequest = async (email: string, password: string): Promise<void> => {
  if (USE_MOCK_API) {
    await signupMock(email, password)
    return
  }
  const api = await loadApiClient()
  await api.post("/api/auth/signup", { email, password })
}

// 메일 링크는 1회용이다. React 개발 모드가 effect를 두 번 실행해도 같은 토큰 요청은 하나로 합친다.
// 끝나면 지운다(같은 링크를 다시 열면 서버에 다시 물어 '이미 사용'을 받아야 하므로).
const verifyInFlight = new Map<string, Promise<void>>()

export const verifyEmailOnce = (token: string): Promise<void> => {
  let pending = verifyInFlight.get(token)
  if (!pending) {
    pending = (async () => {
      if (USE_MOCK_API) {
        await verifyEmailMock(token)
        return
      }
      const api = await loadApiClient()
      await api.post("/api/auth/email/verify", { verificationToken: token })
    })()
    verifyInFlight.set(token, pending)
    const forget = () => verifyInFlight.delete(token)
    pending.then(forget, forget)
  }
  return pending
}

// 가입 여부를 알리지 않는다(항상 202). 429는 재전송 간격·횟수 제한이다.
export const resendVerificationRequest = async (email: string): Promise<void> => {
  if (USE_MOCK_API) {
    await resendVerificationMock(email)
    return
  }
  const api = await loadApiClient()
  await api.post("/api/auth/email/resend", { email })
}

// 가입 여부를 알리지 않고 항상 같은 응답이다.
export const requestPasswordResetRequest = async (email: string): Promise<void> => {
  if (USE_MOCK_API) {
    await requestPasswordResetMock(email)
    return
  }
  const api = await loadApiClient()
  await api.post("/api/auth/password/reset-request", { email })
}

export const resetPasswordRequest = async (token: string, newPassword: string): Promise<void> => {
  if (USE_MOCK_API) {
    await resetPasswordMock(token, newPassword)
    return
  }
  const api = await loadApiClient()
  await api.post("/api/auth/password/reset", { resetToken: token, newPassword })
}

// 로그인 상태에서 비밀번호를 한 번 더 받아 탈퇴한다. 성공 응답(200)을 받아야만 성공으로 본다.
// 응답 본문 모양은 openapi에 없어(계약 없음) 읽지 않는다.
export const deleteAccountRequest = async (password: string): Promise<void> => {
  if (loginsInFlight > 0) throw new AuthOperationConflictError()
  // 어떤 await보다 먼저 잠근다. 이 줄 이후에 시작한 로그인은 탈퇴가 끝날 때까지 기다린다.
  let unlock: () => void = () => {}
  const lock = new Promise<void>((resolve) => {
    unlock = resolve
  })
  accountDeletionInFlight = lock
  try {
    if (USE_MOCK_API) {
      await deleteAccountMock(password)
      return
    }
    const api = await loadApiClient()
    await api.delete("/api/account", { data: { password } })
  } finally {
    unlock()
    if (accountDeletionInFlight === lock) accountDeletionInFlight = null
  }
}
