/**
 * 담당: [A] | 책임: 메모리 Access Token과 401 Refresh 요청 조정.
 * PRD: E5 / 스토리 5-3 / 태스크 5-3-1, 5-3-3.
 * 구현할 기능: 동시 401에서 Refresh를 한 번만 요청하고 성공 시 원 요청을 한 번 재시도한다.
 * 완료 기준: Refresh 실패 시 인증을 해제하고 계정 기록 화면을 숨긴다.
 * 제한사항: Refresh·CSRF 쿠키를 JavaScript에서 읽거나 토큰을 LocalStorage에 저장하지 않는다.
 * 상태: PRD 태스크 미시작. 경로와 응답은 API 승인 후 연결한다.
 */
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios"

interface RetryConfig extends InternalAxiosRequestConfig {
  __retried?: boolean
}
export interface AuthWireContract {
  csrfPath: string
  refreshPath: string
  /** 로그인·가입 등 401이 정상 응답일 수 있는 경로는 Refresh 재시도를 금지한다. */
  noRefreshRetryPaths: readonly string[]
  /** 실제 API JSON 구조는 API 계약 담당자가 작성한다. */
  readCsrfToken(response: AxiosResponse): string
  readAccessToken(response: AxiosResponse): string
}

// 현재 탭의 Access Token을 조회·갱신하고 인증 해제 시 CSRF 토큰도 비운다.
let accessToken: string | null = null
let csrfToken: string | null = null
let csrfPending: Promise<string> | null = null
let refreshPending: Promise<string> | null = null

export const accessSession = {
  get(): string | null {
    return accessToken
  },
  set(token: string): void {
    accessToken = token
  },
  clear(): void {
    accessToken = null
    csrfToken = null
  },
}

// api에 요청·응답 인터셉터를 설치해 CSRF 처리와 메모리 Access Token의 401 갱신을 적용한다.
export function attachAuthSecurity(api: AxiosInstance, wire: AuthWireContract): void {
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
      config.headers.set("X-CSRF-Token", await csrf())
    }
    return config
  })

  api.interceptors.response.use(
    (response) => response,
    async (error: unknown) => {
      const failure = error as { config?: RetryConfig; response?: { status: number } }
      const original = failure.config
      if (
        !original ||
        failure.response?.status !== 401 ||
        original.__retried ||
        original.url === wire.refreshPath ||
        original.url === wire.csrfPath ||
        wire.noRefreshRetryPaths.includes(original.url ?? "")
      ) {
        return Promise.reject(error)
      }
      // Refresh·CSRF 경로와 인증 예외 경로는 위에서 제외하고, 나머지 원 요청만 한 번 재시도한다.
      original.__retried = true
      if (!refreshPending) {
        // 동시 401은 같은 Refresh 응답을 기다려 토큰 회전을 한 번만 수행한다.
        refreshPending = api
          .post(wire.refreshPath, undefined, {
            // API 담당자가 갱신 요청과 응답을 완성한다.
          })
          .then((response) => {
            const token = wire.readAccessToken(response)
            if (!token) throw new Error("Refresh returned no access token")
            accessToken = token
            return token
          })
          .catch((cause) => {
            accessSession.clear()
            throw cause
          })
          .finally(() => {
            refreshPending = null
          })
      }
      await refreshPending
      // Refresh가 끝난 뒤 새 Access Token을 붙여 실패했던 원 요청을 다시 보낸다.
      original.headers.set("Authorization", `Bearer ${accessToken}`)
      return api.request(original)
    },
  )
}

/** 요청별 접속 종료에서 AbortController를 취소한다. SSE는 별도 fetch 구현에서 처리. */
