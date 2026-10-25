/**
 * 담당: [A] | 책임: 메모리 Access Token, CSRF 헤더, 401 Refresh 요청 조정.
 * PRD: E5 / 스토리 5-3 / 태스크 5-3-1, 5-3-3, 4-2-2(계정 ID 추출).
 * 구현: 상태 변경 요청에 X-CSRF-Token을 붙인다. 동시 401에서 Refresh를 한 번만 요청하고 성공하면 원 요청을 한 번 재시도한다.
 *   Refresh가 실패하면 Access Token을 지우고 등록된 리스너(인증 스토어)에 알려 계정 화면을 숨기게 한다.
 * 계약: A14 POST /api/auth/refresh(x-confirmed: true). CSRF 발급 GET /api/auth/csrf → {csrfToken}과
 *   헤더 이름 X-CSRF-Token은 openapi에 없고 Backend 구현(core/security.py)을 따른다(계약 없음).
 * 제한사항: Refresh·CSRF 쿠키를 JavaScript에서 읽거나 토큰을 localStorage·IndexedDB에 저장하지 않는다.
 */
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios"

interface RetryConfig extends InternalAxiosRequestConfig {
  __retried?: boolean
  __csrfRetried?: boolean
}
export interface AuthWireContract {
  csrfPath: string
  refreshPath: string
  /** 로그인·가입 등 401이 정상 응답일 수 있는 경로는 Refresh 재시도를 금지한다. */
  noRefreshRetryPaths: readonly string[]
  readCsrfToken(response: AxiosResponse): string
  readAccessToken(response: AxiosResponse): string
}

// 계약(A11~A16)과 Backend 구현 기준 경로·응답 필드.
export const AUTH_WIRE: AuthWireContract = {
  csrfPath: "/api/auth/csrf",
  refreshPath: "/api/auth/refresh",
  noRefreshRetryPaths: [
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/signup",
    "/api/auth/email/verify",
    "/api/auth/email/resend",
    "/api/auth/password/reset-request",
    "/api/auth/password/reset",
  ],
  readCsrfToken: (response) => (response.data as { csrfToken?: string })?.csrfToken ?? "",
  readAccessToken: (response) => (response.data as { accessToken?: string })?.accessToken ?? "",
}

// 현재 탭의 Access Token을 조회·갱신하고 인증 해제 시 CSRF 토큰도 비운다.
let accessToken: string | null = null
let csrfToken: string | null = null
let csrfPending: Promise<string> | null = null
let refreshPending: Promise<string> | null = null
// Refresh가 실패하면(무효·재사용 탐지) 새 Access Token을 받기 전까지 다시 시도하지 않는다.
// 이미 무효인 Refresh를 401마다 반복하고 인증 해제 알림을 중복 호출하는 것을 막는다.
let refreshFailed = false
let authLostListener: (() => void) | null = null
// 로그인·로그아웃마다 1씩 오르는 세션 번호. 요청을 시작할 때의 번호와 응답이 왔을 때의 번호가 다르면
// 그 응답은 이전 세션 것이므로 버린다. 늦게 끝난 A의 복구·Refresh·로그아웃이 B 로그인 상태를 덮지 못하게 한다.
let sessionEpoch = 0
let refreshRunner: (() => Promise<string>) | null = null

// 이전 세션의 응답이라 버렸음을 알린다.
export class StaleSessionError extends Error {
  constructor() {
    super("stale auth session")
    this.name = "StaleSessionError"
  }
}

const startNewSession = () => {
  sessionEpoch += 1
  // 이전 세션에서 시작한 Refresh를 새 세션이 기다리지 않게 한다.
  refreshPending = null
}

export const accessSession = {
  get(): string | null {
    return accessToken
  },
  current(): number {
    return sessionEpoch
  },
  isCurrent(epoch: number): boolean {
    return epoch === sessionEpoch
  },
  // 로그인 시작. 진행 중인 이전 세션 응답을 무효로 만들고 새 번호를 돌려준다.
  begin(): number {
    startNewSession()
    return sessionEpoch
  },
  // 시작할 때의 번호가 지금과 같을 때만 토큰을 넣는다. 다르면 false(이전 세션 응답).
  setIfCurrent(token: string, epoch: number): boolean {
    if (epoch !== sessionEpoch) return false
    accessToken = token
    refreshFailed = false
    return true
  },
  // 새 세션으로 토큰을 바로 넣는다(테스트·이미 검증된 토큰용).
  set(token: string): void {
    startNewSession()
    accessToken = token
    refreshFailed = false
  },
  // 로그아웃: 서버 응답을 기다리지 않고 즉시 토큰을 지운다. 이후 도착하는 이전 세션 응답은 버린다.
  end(): void {
    startNewSession()
    accessToken = null
    csrfToken = null
  },
  clear(): void {
    accessToken = null
    csrfToken = null
  },
}

// 세션 복구와 401 재시도가 같은 Refresh 실행을 함께 쓴다. 동시에 두 번 보내면 회전형 Refresh 쿠키의
// 재사용 탐지로 정상 로그인이 풀릴 수 있다.
// 실패하면 지금 세션일 때만 인증을 해제하고 화면에 한 번 알린다(5-3-3).
export const refreshAccessToken = (): Promise<string> => {
  if (!refreshRunner) return Promise.reject(new Error("auth security is not attached"))
  if (refreshPending) return refreshPending
  const epoch = sessionEpoch
  const pending: Promise<string> = refreshRunner()
    .then((token) => {
      if (!token) throw new Error("Refresh returned no access token")
      if (epoch !== sessionEpoch) throw new StaleSessionError()
      accessToken = token
      refreshFailed = false
      return token
    })
    .catch((cause) => {
      if (!(cause instanceof StaleSessionError) && epoch === sessionEpoch) {
        refreshFailed = true
        accessToken = null
        csrfToken = null
        authLostListener?.()
      }
      throw cause
    })
    .finally(() => {
      // 그 사이 새 세션이 다른 Refresh를 시작했으면 그것을 지우지 않는다.
      if (refreshPending === pending) refreshPending = null
    })
  refreshPending = pending
  return pending
}

// Refresh 실패로 인증이 끊기면 한 번 호출된다. 인증 스토어가 등록한다.
export const setAuthLostListener = (listener: (() => void) | null) => {
  authLostListener = listener
}

// Access JWT의 sub(사용자 ID)를 읽는다. 서명은 검증하지 않으며 이 기기 저장 영역 구분에만 쓴다(권한 판단에 쓰지 않음).
// 형식이 맞지 않으면 null.
export const accountIdFromAccessToken = (token: string): string | null => {
  const payload = token.split(".")[1]
  if (!payload) return null
  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/")
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4)
    const bytes = Uint8Array.from(atob(padded), (char) => char.charCodeAt(0))
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as { sub?: unknown }
    return typeof claims.sub === "string" && claims.sub.trim() ? claims.sub : null
  } catch {
    return null
  }
}

const readErrorCode = (data: unknown): string | null => {
  const record = data as { code?: unknown; detail?: { code?: unknown } } | null
  const code = record?.detail?.code ?? record?.code
  return typeof code === "string" ? code : null
}

// api에 요청·응답 인터셉터를 설치해 CSRF 처리와 메모리 Access Token의 401 갱신을 적용한다.
export function attachAuthSecurity(api: AxiosInstance, wire: AuthWireContract): void {
  refreshRunner = async () => wire.readAccessToken(await api.post(wire.refreshPath))
  const csrf = async (): Promise<string> => {
    if (csrfToken) return csrfToken
    if (!csrfPending) {
      // 최초 CSRF 발급을 기다리는 동시 변경 요청은 같은 Promise를 기다려 중복 발급을 막는다.
      csrfPending = api
        .get(wire.csrfPath)
        .then((response) => {
          const value = wire.readCsrfToken(response)
          if (!value) throw new Error("CSRF bootstrap returned no token")
          csrfToken = value
          return value
        })
        .finally(() => {
          csrfPending = null
        })
    }
    return csrfPending
  }

  api.interceptors.request.use(async (config) => {
    if (accessToken) config.headers.set("Authorization", `Bearer ${accessToken}`)
    if (["post", "put", "patch", "delete"].includes(config.method?.toLowerCase() ?? "")) {
      // 인증 기능이 꺼진 Backend에는 CSRF 발급 경로가 없다. 발급에 실패해도 Handoff 등 CSRF가 필요 없는 요청은 보낸다.
      // CSRF가 필요한 경로라면 서버가 403으로 거부한다.
      try {
        config.headers.set("X-CSRF-Token", await csrf())
      } catch {
        // 헤더 없이 보낸다.
      }
    }
    return config
  })

  api.interceptors.response.use(
    (response) => response,
    async (error: unknown) => {
      const failure = error as {
        config?: RetryConfig
        response?: { status: number; data?: unknown }
      }
      const original = failure.config
      if (!original) return Promise.reject(error)

      // CSRF 토큰 수명(서버 기본 1시간)이 지나면 403 CSRF_INVALID다. 새로 받아 한 번만 다시 보낸다.
      if (
        failure.response?.status === 403 &&
        readErrorCode(failure.response.data) === "CSRF_INVALID" &&
        !original.__csrfRetried
      ) {
        original.__csrfRetried = true
        csrfToken = null
        return api.request(original)
      }

      if (
        failure.response?.status !== 401 ||
        original.__retried ||
        refreshFailed ||
        original.url === wire.refreshPath ||
        original.url === wire.csrfPath ||
        wire.noRefreshRetryPaths.includes(original.url ?? "")
      ) {
        return Promise.reject(error)
      }
      // Refresh·CSRF 경로와 인증 예외 경로는 위에서 제외하고, 나머지 원 요청만 한 번 재시도한다.
      original.__retried = true
      // 동시 401은 같은 Refresh 응답을 기다려 토큰 회전을 한 번만 수행한다.
      const token = await refreshAccessToken()
      // Refresh가 끝난 뒤 새 Access Token을 붙여 실패했던 원 요청을 다시 보낸다.
      original.headers.set("Authorization", `Bearer ${token}`)
      return api.request(original)
    },
  )
}
