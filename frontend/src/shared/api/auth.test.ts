// 인증 인터셉터 단위 테스트(5-3-1, 5-3-3): 가짜 서버(Axios adapter)로 CSRF·401 Refresh 1회 실행·실패 처리를 확인한다.
// 실제 Backend 호출이 아니다.
import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  AUTH_WIRE,
  accessSession,
  accountIdFromAccessToken,
  attachAuthSecurity,
  setAuthLostListener,
} from "./auth"

type Reply = { status: number; data?: unknown }
type Handler = (config: InternalAxiosRequestConfig) => Reply

// 경로별로 응답을 정하고 호출 기록을 남기는 가짜 서버.
const fakeServer = (handler: Handler) => {
  const calls: { method: string; url: string; headers: Record<string, unknown> }[] = []
  const adapter: AxiosAdapter = async (config) => {
    calls.push({
      method: config.method ?? "get",
      url: config.url ?? "",
      headers: { ...config.headers },
    })
    const reply = handler(config)
    const response = {
      data: reply.data ?? {},
      status: reply.status,
      statusText: String(reply.status),
      headers: {},
      config,
    }
    if (reply.status >= 400) {
      throw Object.assign(new Error(`HTTP ${reply.status}`), { config, response })
    }
    return response
  }
  const api = axios.create({ adapter })
  attachAuthSecurity(api, AUTH_WIRE)
  const count = (method: string, url: string) =>
    calls.filter((call) => call.method === method && call.url === url).length
  return { api, calls, count }
}

const bearer = (config: InternalAxiosRequestConfig) => config.headers.get("Authorization")

beforeEach(() => accessSession.clear())
afterEach(() => setAuthLostListener(null))

describe("401 Refresh single-flight (5-3-1)", () => {
  it("동시 401 여러 건이어도 Refresh는 1번만 하고 각 원 요청을 새 토큰으로 1번씩 다시 보낸다", async () => {
    accessSession.set("old")
    const server = fakeServer((config) => {
      if (config.url === "/api/auth/csrf") return { status: 200, data: { csrfToken: "csrf-1" } }
      if (config.url === "/api/auth/refresh") return { status: 200, data: { accessToken: "new" } }
      return bearer(config) === "Bearer new" ? { status: 200, data: { ok: true } } : { status: 401 }
    })

    const results = await Promise.all([
      server.api.get("/api/a"),
      server.api.get("/api/b"),
      server.api.get("/api/c"),
    ])

    expect(results.map((r) => r.status)).toEqual([200, 200, 200])
    expect(server.count("post", "/api/auth/refresh")).toBe(1)
    expect(server.count("get", "/api/a")).toBe(2)
    expect(accessSession.get()).toBe("new")
  })

  it("Refresh가 실패하면 반복하지 않고 인증을 해제한 뒤 리스너에 한 번 알린다(5-3-3)", async () => {
    accessSession.set("old")
    const lost = vi.fn()
    setAuthLostListener(lost)
    const server = fakeServer((config) => {
      if (config.url === "/api/auth/csrf") return { status: 200, data: { csrfToken: "csrf-1" } }
      if (config.url === "/api/auth/refresh")
        return { status: 401, data: { code: "REFRESH_INVALID" } }
      return { status: 401 }
    })

    const results = await Promise.allSettled([server.api.get("/api/a"), server.api.get("/api/b")])

    expect(results.every((r) => r.status === "rejected")).toBe(true)
    expect(server.count("post", "/api/auth/refresh")).toBe(1)
    expect(lost).toHaveBeenCalledTimes(1)
    expect(accessSession.get()).toBeNull()
  })

  it("로그인 경로의 401은 Refresh하지 않고 그대로 실패로 돌려준다", async () => {
    const server = fakeServer((config) =>
      config.url === "/api/auth/csrf"
        ? { status: 200, data: { csrfToken: "csrf-1" } }
        : { status: 401, data: { code: "UNAUTHENTICATED" } },
    )

    await expect(server.api.post("/api/auth/login", {})).rejects.toMatchObject({
      response: { status: 401 },
    })
    expect(server.count("post", "/api/auth/refresh")).toBe(0)
  })
})

describe("CSRF", () => {
  it("상태 변경 요청에 X-CSRF-Token을 붙이고, 동시 요청에도 발급은 1번만 한다", async () => {
    const server = fakeServer((config) =>
      config.url === "/api/auth/csrf"
        ? { status: 200, data: { csrfToken: "csrf-1" } }
        : { status: 200 },
    )

    await Promise.all([server.api.post("/api/x"), server.api.post("/api/y")])

    expect(server.count("get", "/api/auth/csrf")).toBe(1)
    const posts = server.calls.filter((call) => call.method === "post")
    expect(posts.every((call) => call.headers["X-CSRF-Token"] === "csrf-1")).toBe(true)
  })

  it("CSRF 발급 경로가 없는 Backend(인증 꺼짐)에서도 Handoff 같은 POST는 헤더 없이 보낸다", async () => {
    const server = fakeServer((config) =>
      config.url === "/api/auth/csrf" ? { status: 404 } : { status: 200, data: { ok: true } },
    )

    const response = await server.api.post("/api/handoff/exchange", { token: "t" })

    expect(response.status).toBe(200)
    const post = server.calls.find((call) => call.url === "/api/handoff/exchange")
    expect(post?.headers["X-CSRF-Token"]).toBeUndefined()
  })

  it("403 CSRF_INVALID면 CSRF를 새로 받아 한 번만 다시 보낸다", async () => {
    let issued = 0
    const server = fakeServer((config) => {
      if (config.url === "/api/auth/csrf") {
        issued += 1
        return { status: 200, data: { csrfToken: `csrf-${issued}` } }
      }
      return config.headers.get("X-CSRF-Token") === "csrf-2"
        ? { status: 200 }
        : { status: 403, data: { code: "CSRF_INVALID" } }
    })

    const response = await server.api.post("/api/x")

    expect(response.status).toBe(200)
    expect(server.count("get", "/api/auth/csrf")).toBe(2)
    expect(server.count("post", "/api/x")).toBe(2)
  })
})

describe("accountIdFromAccessToken", () => {
  const jwt = (claims: object) =>
    `h.${btoa(JSON.stringify(claims)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.s`

  it("Access JWT의 sub를 읽는다", () => {
    expect(accountIdFromAccessToken(jwt({ sub: "user-123", exp: 1 }))).toBe("user-123")
  })

  it("sub가 없거나 형식이 깨지면 null이다", () => {
    expect(accountIdFromAccessToken(jwt({ exp: 1 }))).toBeNull()
    expect(accountIdFromAccessToken("not-a-jwt")).toBeNull()
    expect(accountIdFromAccessToken("a.!!!.c")).toBeNull()
  })
})
