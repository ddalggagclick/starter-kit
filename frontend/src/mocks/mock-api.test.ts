import { beforeEach, describe, expect, it } from "vitest"
import { createMockAskResponse, type MockAiScenario } from "./ai-stream"
import { findRiskGuidance } from "./checklist"
import {
  deleteAccount,
  deleteMyChecklist,
  exchangeHandoff,
  getMyChecklist,
  getProcedure,
  listProcedures,
  login,
  MOCK_ACCOUNT,
  MOCK_VALID_HANDOFF_TOKEN,
  MOCK_VALID_RESET_TOKEN,
  MOCK_VALID_VERIFY_TOKEN,
  MockHttpError,
  putMyChecklist,
  resetMockApiState,
  resetPassword,
  signup,
  verifyEmail,
} from "./mock-api"
import type { SseEvent } from "./wire-types"

const fast = { latencyMs: 0 }

// 테스트 전용 최소 SSE 파서. 실제 파서는 use-chat-stream 책임이다.
const readSseEvents = async (response: Response): Promise<SseEvent[]> => {
  const text = await response.text()
  return text
    .split("\n\n")
    .filter(Boolean)
    .map((block) => {
      const event = block.match(/^event: (.+)$/m)?.[1]
      const data = block.match(/^data: (.+)$/m)?.[1] ?? "null"
      return { event, data: JSON.parse(data) } as SseEvent
    })
}

const ask = (scenario: MockAiScenario, question = "상속포기 기한이 언제부터인가요?") =>
  createMockAskResponse({ question, requestId: "req-1" }, { scenario, stepDelayMs: 0 })

beforeEach(() => resetMockApiState())

describe("A07 절차 Mock", () => {
  it("절차 8개를 모두 돌려준다", async () => {
    const { procedures } = await listProcedures(fast)
    expect(procedures.map((item) => item.procedureId)).toEqual([
      "p01",
      "p02",
      "p03",
      "p04",
      "p05",
      "p06",
      "p07",
      "p08",
    ])
  })

  it("관련 절차는 D4 보류라 비어 있고, p02를 뺀 절차는 공식 링크가 있다", async () => {
    for (const { procedureId } of (await listProcedures(fast)).procedures) {
      const detail = await getProcedure(procedureId, fast)
      expect(detail.relatedProcedureIds).toEqual([])
      // p02는 팀 시트 주소가 발급 신청 화면이라 링크를 넣지 않기로 했다(2026-10-22 원고 결정).
      if (procedureId === "p02") expect(detail.officialLinks).toEqual([])
      else expect(detail.officialLinks.length).toBeGreaterThan(0)
    }
  })

  it("없는 절차 ID는 422", async () => {
    await expect(getProcedure("p99", fast)).rejects.toMatchObject({ status: 422 })
  })
})

describe("A05 Handoff Mock", () => {
  it("유효 토큰은 1회만 성공하고 재사용은 같은 400", async () => {
    await expect(exchangeHandoff(MOCK_VALID_HANDOFF_TOKEN, fast)).resolves.toMatchObject({
      relationship: "descendant",
      deathDateUnknown: false,
    })
    const reuse = exchangeHandoff(MOCK_VALID_HANDOFF_TOKEN, fast)
    const unknown = exchangeHandoff("expired", fast)
    await expect(reuse).rejects.toMatchObject({ status: 400, body: { code: "HANDOFF_INVALID" } })
    await expect(unknown).rejects.toMatchObject({ status: 400, body: { code: "HANDOFF_INVALID" } })
  })
})

describe("A13 로그인 Mock", () => {
  it("성공 시 15분 Access, 5번 실패 후 429", async () => {
    await expect(login(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password, fast)).resolves.toEqual({
      accessToken: "mock-access-token",
      expiresIn: 900,
    })
    for (let i = 0; i < 5; i += 1) {
      await expect(login(MOCK_ACCOUNT.email, "wrong1234", fast)).rejects.toMatchObject({
        status: 401,
      })
    }
    const limited = await login(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password, fast).catch((e) => e)
    expect(limited).toBeInstanceOf(MockHttpError)
    expect(limited.status).toBe(429)
  })
})

describe("A08 AI SSE Mock", () => {
  it("answered: status 후 result 1번, 출처 있음", async () => {
    const response = await ask("answered")
    expect(response.headers.get("Content-Type")).toBe("text/event-stream")
    const events = await readSseEvents(response)
    expect(events.filter((e) => e.event === "result")).toHaveLength(1)
    const last = events.at(-1)
    expect(last?.event).toBe("result")
    if (last?.event === "result") expect(last.data.sources.length).toBeGreaterThan(0)
  })

  it("withheld: 출처 0개면 답변 null (S7, 오류 아님)", async () => {
    const response = await ask("withheld")
    expect(response.status).toBe(200)
    const last = (await readSseEvents(response)).at(-1)
    expect(last).toMatchObject({
      event: "result",
      data: { state: "withheld", answer: null, sources: [] },
    })
  })

  it("스트림 시작 전 오류는 HTTP 상태로 돌려준다", async () => {
    expect((await ask("guestLimit")).status).toBe(429)
    expect((await ask("providerUnavailable")).status).toBe(503)
  })

  it("스트림 중 오류는 error 이벤트로 끝난다", async () => {
    const last = (await readSseEvents(await ask("providerTimeout"))).at(-1)
    expect(last).toMatchObject({ event: "error", data: { code: "PROVIDER_TIMEOUT" } })
  })

  it("200 코드 포인트 초과는 자르지 않고 422", async () => {
    const response = await ask("answered", "😀".repeat(201))
    expect(response.status).toBe(422)
    // 이모지 200개는 UTF-16 길이 400이지만 코드 포인트 기준이라 허용된다.
    expect((await ask("answered", "😀".repeat(200))).status).toBe(200)
  })
})

describe("위험 안내 문구", () => {
  it("승인 문구가 없는 답은 null (공통 경고만 표시)", () => {
    expect(findRiskGuidance("debt", "yes")).not.toBeNull()
    expect(findRiskGuidance("debt", "no")).toBeNull()
    expect(findRiskGuidance("self_application", "unknown")).toBeNull()
  })
})

describe("Mock 계정 상태 반영 (리뷰 회귀)", () => {
  beforeEach(() => resetMockApiState())

  it("비밀번호 재설정에 성공하면 새 비밀번호로만 로그인된다", async () => {
    await resetPassword(MOCK_VALID_RESET_TOKEN, "changed123", fast)

    await expect(login(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password, fast)).rejects.toMatchObject({
      status: 401,
    })
    await expect(login(MOCK_ACCOUNT.email, "changed123", fast)).resolves.toMatchObject({
      accessToken: expect.any(String),
    })
  })

  it("탈퇴하면 로그인할 수 없고, 다시 탈퇴하면 401이며, 같은 이메일로 다시 가입할 수 있다", async () => {
    await deleteAccount(MOCK_ACCOUNT.password, fast)

    await expect(login(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password, fast)).rejects.toMatchObject({
      status: 401,
    })
    await expect(deleteAccount(MOCK_ACCOUNT.password, fast)).rejects.toMatchObject({ status: 401 })
    await expect(signup(MOCK_ACCOUNT.email, "newpass123", fast)).resolves.toEqual({ status: 201 })
  })

  it("탈퇴 후 같은 이메일로 재가입하면 메일 인증 전에는 로그인할 수 없고, 인증 후 새 비밀번호로 로그인된다", async () => {
    await deleteAccount(MOCK_ACCOUNT.password, fast)
    await signup(MOCK_ACCOUNT.email, "rejoin123", fast)

    // 실제 Backend와 같이 비밀번호가 맞아도 미인증이면 401 + 안내 문장
    await expect(login(MOCK_ACCOUNT.email, "rejoin123", fast)).rejects.toMatchObject({
      status: 401,
      body: { message: "이메일 인증 후 로그인할 수 있습니다." },
    })

    await verifyEmail(MOCK_VALID_VERIFY_TOKEN, fast)

    await expect(login(MOCK_ACCOUNT.email, MOCK_ACCOUNT.password, fast)).rejects.toMatchObject({
      status: 401,
    })
    await expect(login(MOCK_ACCOUNT.email, "rejoin123", fast)).resolves.toMatchObject({
      accessToken: expect.any(String),
    })
  })

  it("탈퇴는 현재 비밀번호(재설정 후 값)로만 된다", async () => {
    await resetPassword(MOCK_VALID_RESET_TOKEN, "changed123", fast)

    await expect(deleteAccount(MOCK_ACCOUNT.password, fast)).rejects.toBeInstanceOf(MockHttpError)
    await expect(deleteAccount("changed123", fast)).resolves.toMatchObject({ account: "deleted" })
  })
})

describe("A17 Mock 계정별 분리", () => {
  beforeEach(() => resetMockApiState())

  it("A 계정의 서버 체크리스트는 B 계정에서 조회되지 않고, A 삭제가 B에 영향을 주지 않는다", async () => {
    await putMyChecklist("user-a", { itemStates: [{ a: 1 }], serverSaveConsent: true }, fast)
    await putMyChecklist("user-b", { itemStates: [{ b: 1 }], serverSaveConsent: true }, fast)

    await deleteMyChecklist("user-a", fast)

    await expect(getMyChecklist("user-a", fast)).rejects.toMatchObject({ status: 403 })
    await expect(getMyChecklist("user-b", fast)).resolves.toEqual({
      itemStates: [{ b: 1 }],
      serverSaveConsent: true,
    })
  })

  it("로그인하지 않으면 401이다", async () => {
    await expect(getMyChecklist(null, fast)).rejects.toMatchObject({ status: 401 })
  })
})
