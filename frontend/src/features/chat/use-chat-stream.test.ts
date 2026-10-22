// @vitest-environment jsdom
// SSE 파서와 useChatStream 단위 테스트 (Mock Response 사용. 실제 A08 Backend 연동 결과가 아니다).
import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { createMockAskResponse, type MockAiScenario } from "@/mocks/ai-stream"
import { readSseEvents } from "./sse-parser"
import { type ChatTransport, useChatStream } from "./use-chat-stream"

const streamOf = (chunks: string[]) =>
  new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder()
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })

const collect = async (chunks: string[]) => {
  const events = []
  for await (const event of readSseEvents(streamOf(chunks))) events.push(event)
  return events
}

const mockTransport =
  (scenario: MockAiScenario): ChatTransport =>
  (request, signal) =>
    createMockAskResponse(request, { scenario, signal, stepDelayMs: 0 })

describe("readSseEvents", () => {
  it("청크 경계가 이벤트 중간에 걸려도 이어 붙여 읽는다", async () => {
    const events = await collect([
      'event: status\ndata: {"stage":"sear',
      'ching"}\n\nevent: result\r\ndata: {"a":1}\r\n\r\n',
    ])
    expect(events).toEqual([
      { event: "status", data: '{"stage":"searching"}' },
      { event: "result", data: '{"a":1}' },
    ])
  })

  it("주석 줄은 무시하고 마지막 빈 줄이 없어도 남은 이벤트를 읽는다", async () => {
    const events = await collect([": keep-alive\n\nevent: error\ndata: x"])
    expect(events).toEqual([{ event: "error", data: "x" }])
  })
})

describe("useChatStream", () => {
  it("answered 결과를 돌려준다", async () => {
    const { result } = renderHook(() => useChatStream(mockTransport("answered")))
    let outcome: Awaited<ReturnType<typeof result.current.ask>> = null
    await act(async () => {
      outcome = await result.current.ask("상속포기 기한은?", [])
    })
    expect(outcome).toMatchObject({ kind: "answered" })
    expect(result.current.running).toBe(false)
  })

  it("출처 0건이면 withheld(S7)", async () => {
    const { result } = renderHook(() => useChatStream(mockTransport("withheld")))
    await act(async () => {
      expect(await result.current.ask("질문", [])).toMatchObject({ kind: "withheld" })
    })
  })

  it("스트림 시작 전 오류(503)와 스트림 중 오류(PROVIDER_TIMEOUT)를 error로 돌려준다", async () => {
    const unavailable = renderHook(() => useChatStream(mockTransport("providerUnavailable")))
    await act(async () => {
      expect(await unavailable.result.current.ask("질문", [])).toEqual({
        kind: "error",
        failure: expect.objectContaining({ status: 503, code: "PROVIDER_UNAVAILABLE" }),
      })
    })
    const timeout = renderHook(() => useChatStream(mockTransport("providerTimeout")))
    await act(async () => {
      expect(await timeout.result.current.ask("질문", [])).toEqual({
        kind: "error",
        failure: expect.objectContaining({ code: "PROVIDER_TIMEOUT" }),
      })
    })
  })

  it("취소한 요청의 늦은 결과는 null로 버린다", async () => {
    const slow: ChatTransport = (request, signal) =>
      createMockAskResponse(request, { scenario: "answered", signal, stepDelayMs: 30 })
    const { result } = renderHook(() => useChatStream(slow))
    let pending: Promise<unknown> = Promise.resolve()
    act(() => {
      pending = result.current.ask("질문", [])
    })
    act(() => result.current.cancel())
    await act(async () => {
      expect(await pending).toBeNull()
    })
    expect(result.current.running).toBe(false)
  })
})
