// A08 실제 전송 단위 테스트: 요청 모양(경로·헤더·본문·쿠키·취소 신호)만 확인한다. 실제 Backend 호출이 아니다.
import { afterEach, describe, expect, it, vi } from "vitest"
import { accessSession } from "@/shared/api/auth"
import { ASK_PATH, createApiAskTransport } from "./ask-transport"

afterEach(() => {
  vi.unstubAllGlobals()
  accessSession.clear()
})

const stubFetch = () => {
  const fetchMock = vi.fn(async () => new Response("", { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

describe("createApiAskTransport", () => {
  it("계약대로 POST 본문과 SSE Accept·쿠키 전송·취소 신호를 붙인다", async () => {
    const fetchMock = stubFetch()
    const controller = new AbortController()

    await createApiAskTransport("http://localhost:8000")(
      { question: "상속포기 기한", requestId: "req-1", previousQuestions: ["무엇부터 할까요?"] },
      controller.signal,
    )

    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit]
    expect(url.toString()).toBe(`http://localhost:8000${ASK_PATH}`)
    expect(init.method).toBe("POST")
    expect(init.credentials).toBe("include")
    expect(init.signal).toBe(controller.signal)
    expect(init.headers).toMatchObject({ Accept: "text/event-stream" })
    expect(init.headers).not.toHaveProperty("Authorization")
    expect(JSON.parse(init.body as string)).toEqual({
      question: "상속포기 기한",
      requestId: "req-1",
      previousQuestions: ["무엇부터 할까요?"],
    })
  })

  it("이전 질문이 없으면 빈 배열을 보내고, 로그인 중이면 Access Token을 붙인다", async () => {
    const fetchMock = stubFetch()
    accessSession.set("access-token")

    await createApiAskTransport("http://localhost:8000")(
      { question: "상속세", requestId: "req-2" },
      new AbortController().signal,
    )

    const init = (fetchMock.mock.calls[0] as unknown as [URL, RequestInit])[1]
    expect(JSON.parse(init.body as string).previousQuestions).toEqual([])
    expect(init.headers).toMatchObject({ Authorization: "Bearer access-token" })
  })

  it("API 주소가 없거나 절대 주소가 아니면 요청하지 않고 실패한다", async () => {
    const fetchMock = stubFetch()

    await expect(
      createApiAskTransport(undefined)(
        { question: "q", requestId: "r" },
        new AbortController().signal,
      ),
    ).rejects.toThrow()
    await expect(
      createApiAskTransport("/relative")(
        { question: "q", requestId: "r" },
        new AbortController().signal,
      ),
    ).rejects.toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
