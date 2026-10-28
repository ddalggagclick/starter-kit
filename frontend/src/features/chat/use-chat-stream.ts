/*
 * 담당: [A] | 책임: POST SSE 진행·완료 응답 수신과 요청 취소.
 * PRD: E3 / 스토리 3-5, 3-4 / 태스크 3-5-1, 3-5-2; 수신 연계 3-4-3.
 * 구현: 요청마다 requestId와 AbortController를 만든다. 실제 status 이벤트만 진행 단계로 보여주고,
 *   result/error 한 건으로 끝낸다. 취소·화면 이탈·새 요청이 오면 이전 요청을 끊고 늦은 응답을 버린다.
 *   result가 answered여도 답변 본문이나 출처가 없으면 S7(판단 유보)로 처리한다(출처 0건 → S7).
 * 제한사항: 전송 방식(transport)은 바깥에서 받는다. 실제 A08은 ask-transport.ts, Mock은 mocks/ai-stream.ts다.
 *   화면 타이핑 효과와 출처 표시는 chat-page 책임이다.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import { type ApiFailure, readErrorJson } from "@/shared/api/api-error"
import type { SseErrorEvent, SseResultEvent, SseStatusEvent } from "@/shared/api/types"
import { readSseEvents } from "./sse-parser"

export type AskRequest = { question: string; requestId: string; previousQuestions?: string[] }
export type ChatTransport = (request: AskRequest, signal: AbortSignal) => Promise<Response>
export type SseStage = SseStatusEvent["stage"]

export type ChatOutcome =
  | { kind: "answered"; result: SseResultEvent }
  | { kind: "withheld"; result: SseResultEvent }
  | { kind: "error"; failure: ApiFailure }

const NO_RESPONSE: ApiFailure = { status: 0, code: null, message: null }

const newRequestId = () =>
  globalThis.crypto?.randomUUID?.() ?? `req-${Date.now()}-${Math.random().toString(16).slice(2)}`

const toOutcome = (result: SseResultEvent): ChatOutcome =>
  result.state === "answered" && result.answer && (result.sources?.length ?? 0) > 0
    ? { kind: "answered", result }
    : { kind: "withheld", result }

export const useChatStream = (transport: ChatTransport) => {
  const [stage, setStage] = useState<SseStage | null>(null)
  const [running, setRunning] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const activeRequestId = useRef<string | null>(null)

  const cancel = useCallback(() => {
    activeRequestId.current = null
    controllerRef.current?.abort()
    controllerRef.current = null
    setRunning(false)
    setStage(null)
  }, [])

  // 화면을 떠나면 진행 중 요청을 끊는다(3-5-2).
  useEffect(() => cancel, [cancel])

  // 결과를 돌려준다. 취소되었거나 더 새 요청에 밀렸으면 null(화면에 반영하지 않음).
  const ask = useCallback(
    async (question: string, previousQuestions: string[]): Promise<ChatOutcome | null> => {
      controllerRef.current?.abort()
      const controller = new AbortController()
      const requestId = newRequestId()
      controllerRef.current = controller
      activeRequestId.current = requestId
      const isCurrent = () => activeRequestId.current === requestId && !controller.signal.aborted
      setRunning(true)
      setStage(null)
      try {
        const response = await transport(
          { question, requestId, previousQuestions },
          controller.signal,
        )
        if (!isCurrent()) return null
        if (!response.ok || !response.body) {
          return { kind: "error", failure: await readErrorJson(response) }
        }
        for await (const event of readSseEvents(response.body)) {
          if (!isCurrent()) return null
          if (event.event === "status") {
            setStage((JSON.parse(event.data) as SseStatusEvent).stage)
          } else if (event.event === "result") {
            return toOutcome(JSON.parse(event.data) as SseResultEvent)
          } else if (event.event === "error") {
            const data = JSON.parse(event.data) as SseErrorEvent
            return {
              kind: "error",
              failure: { status: 200, code: data.code, message: data.message },
            }
          }
        }
        // result 없이 스트림이 끝나면 기술 오류로 본다(미검증 본문을 보여주지 않는다).
        return isCurrent() ? { kind: "error", failure: NO_RESPONSE } : null
      } catch {
        return isCurrent() ? { kind: "error", failure: NO_RESPONSE } : null
      } finally {
        if (activeRequestId.current === requestId) {
          activeRequestId.current = null
          controllerRef.current = null
          setRunning(false)
          setStage(null)
        }
      }
    },
    [transport],
  )

  return { ask, cancel, running, stage }
}
