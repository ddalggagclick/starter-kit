// @vitest-environment jsdom
// 5-3-1 보강: 재발급받은 Access 토큰은 메모리(accessSession)에만 있고 브라우저 저장소에 남지 않는다.
// 공통 Axios 인스턴스는 withCredentials로 Refresh·CSRF 쿠키를 함께 보낸다. 가짜 서버(Axios adapter)로 시험하며 실제 Backend가 아니다.
// 교차 사이트 쿠키 실브라우저 검증과 CHIPS 판단은 백엔드 배포 주소가 정해진 뒤 따로 한다.
import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AUTH_WIRE, accessSession, attachAuthSecurity } from "./auth"

beforeEach(() => accessSession.clear())
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe("Access 토큰 메모리 보관 (5-3-1)", () => {
  it("401 뒤 Refresh로 받은 새 토큰은 메모리에만 있고 localStorage·sessionStorage·IndexedDB·쿠키에 쓰지 않는다", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const idbOpen = vi.fn()
    vi.stubGlobal("indexedDB", { open: idbOpen })
    const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
      const reply =
        config.url === "/api/auth/refresh"
          ? { status: 200, data: { accessToken: "fresh-access-token" } }
          : config.headers.get("Authorization") === "Bearer fresh-access-token"
            ? { status: 200, data: { ok: true } }
            : { status: 401, data: {} }
      const response = { ...reply, statusText: "", headers: {}, config }
      if (reply.status >= 400) throw Object.assign(new Error("401"), { config, response })
      return response
    }
    const api = axios.create({ adapter })
    attachAuthSecurity(api, AUTH_WIRE)
    accessSession.set("expired-access-token")

    expect((await api.get("/api/me")).status).toBe(200)

    expect(accessSession.get()).toBe("fresh-access-token")
    expect(setItem).not.toHaveBeenCalled()
    expect(idbOpen).not.toHaveBeenCalled()
    expect(JSON.stringify({ ...localStorage })).not.toContain("fresh-access-token")
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("fresh-access-token")
    expect(document.cookie).not.toContain("fresh-access-token")
  })
})

describe("쿠키 전송 설정 (5-3-1)", () => {
  it("공통 Axios 인스턴스는 withCredentials로 Refresh·CSRF 쿠키를 함께 보낸다", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000")
    const { api } = await import("./client")

    expect(api.defaults.withCredentials).toBe(true)
    expect(api.defaults.baseURL).toBe("http://localhost:8000")
  })
})
