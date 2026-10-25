// 인증 인터셉터 단위 테스트(5-3-1, 5-3-3): 가짜 서버(Axios adapter)로 CSRF·401 Refresh 1회 실행·실패 처리를 확인한다.
// 실제 Backend 호출이 아니다.
import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  AUTH_WIRE,
  accessSession,
  accountIdFromAccessToken,
  attachAuthSecurity,
  refreshAccessToken,
  StaleSessionError,
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

  it("Refresh가 한 번 실패한 뒤 새 401이 와도 Refresh를 다시 하지 않고 알림도 중복하지 않는다", async () => {
    accessSession.set("old")
    const lost = vi.fn()
    setAuthLostListener(lost)
    const server = fakeServer((config) => {
      if (config.url === "/api/auth/csrf") return { status: 200, data: { csrfToken: "csrf-1" } }
      if (config.url === "/api/auth/refresh")
        return { status: 401, data: { code: "REFRESH_INVALID" } }
      return { status: 401 }
    })

    await server.api.get("/api/a").catch(() => undefined)
    await server.api.get("/api/b").catch(() => undefined)
    await server.api.get("/api/c").catch(() => undefined)

    expect(server.count("post", "/api/auth/refresh")).toBe(1)
    expect(lost).toHaveBeenCalledTimes(1)
    expect(server.count("get", "/api/b")).toBe(1)
  })

  it("Refresh 실패 뒤 다시 로그인해 새 토큰을 받으면 이후 401은 다시 Refresh한다", async () => {
    accessSession.set("old")
    let refreshOk = false
    const server = fakeServer((config) => {
      if (config.url === "/api/auth/csrf") return { status: 200, data: { csrfToken: "csrf-1" } }
      if (config.url === "/api/auth/refresh")
        return refreshOk
          ? { status: 200, data: { accessToken: "fresh" } }
          : { status: 401, data: { code: "REFRESH_INVALID" } }
      return bearer(config) === "Bearer fresh" ? { status: 200 } : { status: 401 }
    })
    await server.api.get("/api/a").catch(() => undefined)

    // 다시 로그인: 새 Access Token을 세션에 넣는다(만료됐다고 가정해 401 → Refresh 성공).
    accessSession.set("relogin")
    refreshOk = true
    const response = await server.api.get("/api/b")

    expect(response.status).toBe(200)
    expect(server.count("post", "/api/auth/refresh")).toBe(2)
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

describe("늦게 도착한 이전 세션 응답 (리뷰 회귀)", () => {
  // Refresh 응답을 테스트가 원하는 때에 돌려주는 서버.
  const deferredRefreshServer = () => {
    let release: (token: string) => void = () => {}
    let refreshCalls = 0
    const adapter: AxiosAdapter = async (config) => {
      const reply = (status: number, data: unknown) => ({
        data,
        status,
        statusText: "",
        headers: {},
        config,
      })
      if (config.url === "/api/auth/csrf") return reply(200, { csrfToken: "csrf" })
      if (config.url === "/api/auth/refresh") {
        refreshCalls += 1
        const token = await new Promise<string>((resolve) => {
          release = resolve
        })
        return reply(200, { accessToken: token })
      }
      const response = reply(401, {})
      throw Object.assign(new Error("401"), { config, response })
    }
    const api = axios.create({ adapter })
    attachAuthSecurity(api, AUTH_WIRE)
    // Refresh 요청은 CSRF 발급을 거쳐 서버에 도착한다. 도착을 확인한 뒤에 응답을 보낸다.
    const respond = async (token: string) => {
      await vi.waitFor(() => expect(refreshCalls).toBe(1))
      release(token)
    }
    return { api, respond, calls: () => refreshCalls }
  }

  it("A 세션의 Refresh가 B 로그인 뒤에 끝나도 B 토큰을 덮지 않고 인증 해제 알림도 없다", async () => {
    const lost = vi.fn()
    setAuthLostListener(lost)
    const server = deferredRefreshServer()
    accessSession.set("a-old")
    const pending = refreshAccessToken()

    // B 로그인 완료
    const epoch = accessSession.begin()
    expect(accessSession.setIfCurrent("b-token", epoch)).toBe(true)
    await server.respond("a-new")

    await expect(pending).rejects.toBeInstanceOf(StaleSessionError)
    expect(accessSession.get()).toBe("b-token")
    expect(lost).not.toHaveBeenCalled()
  })

  it("로그아웃 뒤 도착한 Refresh 결과는 토큰을 다시 넣지 않는다", async () => {
    const server = deferredRefreshServer()
    accessSession.set("a-old")
    const pending = refreshAccessToken()

    accessSession.end()
    await server.respond("a-new")

    await expect(pending).rejects.toBeInstanceOf(StaleSessionError)
    expect(accessSession.get()).toBeNull()
  })

  it("세션 복구와 401 재시도가 겹쳐도 Refresh는 1번만 보낸다", async () => {
    const server = deferredRefreshServer()
    accessSession.set("old")

    const restore = refreshAccessToken()
    const request = server.api.get("/api/a").catch(() => undefined)
    await server.respond("new")
    await restore
    await request

    expect(server.calls()).toBe(1)
    expect(accessSession.get()).toBe("new")
  })
})
