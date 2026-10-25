import { beforeEach, describe, expect, it } from "vitest"
import { createMockAskResponse, type MockAiScenario } from "./ai-stream"
import { findRiskGuidance } from "./checklist"
import {
  exchangeHandoff,
  getProcedure,
  listProcedures,
  login,
  MOCK_ACCOUNT,
  MOCK_VALID_HANDOFF_TOKEN,
  MockHttpError,
  resetMockApiState,
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
