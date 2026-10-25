/*
 * 담당: [A] | 책임: A08 POST /api/ai/ask 실제 전송(fetch + ReadableStream).
 * PRD: E3 / 태스크 3-5-1, 3-5-2. API: A08 (openapi 0.2.1 x-confirmed: true, 경로 제안).
 * 구현: 요청 본문 {question, requestId, previousQuestions}를 보내고 text/event-stream Response를 그대로 돌려준다.
 *   SSE 해석·오류 분기·늦은 응답 차단은 use-chat-stream이 한다. 로그인 중이면 메모리 Access Token을 붙인다.
 * 제한사항: SSE는 Axios를 쓰지 않는다(CLAUDE.md). 질문 원문을 로그에 남기지 않는다.
 */
import { accessSession } from "@/shared/api/auth"
import type { ChatTransport } from "./use-chat-stream"

export const ASK_PATH = "/api/ai/ask"

// 주소가 잘못 설정되면 요청 전에 실패시켜 화면이 S6(기술 오류)로 처리하게 한다.
export const createApiAskTransport =
  (baseUrl: string | undefined = import.meta.env.VITE_API_BASE_URL): ChatTransport =>
  async (request, signal) => {
    if (!baseUrl || !/^https?:\/\//.test(baseUrl)) {
      throw new Error("VITE_API_BASE_URL must be an absolute API origin")
    }
    const token = accessSession.get()
    return fetch(new URL(ASK_PATH, baseUrl), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        question: request.question,
        requestId: request.requestId,
        previousQuestions: request.previousQuestions ?? [],
      }),
      // 별도 Origin Backend로 Refresh 쿠키가 함께 가도록 한다(공통 Axios의 withCredentials와 같은 정책).
      credentials: "include",
      signal,
    })
  }
