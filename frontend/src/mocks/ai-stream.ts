/*
 * 담당: [A] | 책임: A08 POST /api/ai/ask SSE 응답 Mock (W-07 S1~S9 화면 확인용).
 * 근거: openapi.yaml A08·SseEvents, 화면정의서 v1.4 08·14장, 부록3·4, PRD 3-1-5.
 * 구현: 실제 fetch가 받는 것과 같은 text/event-stream Response를 만든다. 스트림 시작 전 오류는
 *   HTTP 상태 + JSON, 시작 후 오류는 error 이벤트로 보낸다. signal을 끊으면 스트림을 멈춘다.
 * 제한사항: 실제 Gemini·RAG 호출이 아니며 답변·출처는 예시다. AI 실동작 완료로 표시하지 않는다.
 */
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import {
  type AskAiRequest,
  type ErrorBody,
  RATE_LIMIT_REASONS,
  type SseErrorEvent,
  type SseEvent,
  type SseResultEvent,
  type SseSource,
} from "./wire-types"

export type MockAiScenario =
  | "answered"
  | "answeredSingleSource"
  | "answeredNoUrlSource"
  | "withheld"
  | "providerUnavailable"
  | "providerTimeout"
  | "guestLimit"
  | "memberMinuteLimit"
  | "providerRateLimit"

// 각 시나리오가 화면정의서의 어느 상태로 가는지 Mock 패널에 보여준다.
export const MOCK_AI_SCENARIO_LABELS: Record<MockAiScenario, string> = {
  answered: "S3 답변 · 출처 3개 (2개 + 추가 출처 보기)",
  answeredSingleSource: "S3 답변 · 출처 1개",
  answeredNoUrlSource: "S3 답변 · 링크 없는 출처 포함 (url null)",
  withheld: "S7 판단 유보 · 출처 0개",
  providerUnavailable: "S6 기술 오류 · 503 PROVIDER_UNAVAILABLE",
  providerTimeout: "S6 기술 오류 · 504 PROVIDER_TIMEOUT (스트림 중)",
  guestLimit: "S9 사용 제한 · 429 RATE_LIMITED (비로그인 하루 10회, GUEST_DAILY_LIMIT)",
  memberMinuteLimit: "S9 사용 제한 · 429 RATE_LIMITED (로그인 1분 10회, MEMBER_MINUTE_LIMIT)",
  providerRateLimit: "S9 사용 제한 · PROVIDER_RATE_LIMIT (스트림 중)",
}

// 화면정의서 08장 S1 예시 질문. 누르면 입력칸만 채운다(PRD 3-1-1).
export const MOCK_EXAMPLE_QUESTIONS = [
  "무엇부터 할까요?",
  "상속세",
  "상속포기 기한이 언제부터인가요?",
]

// 개인정보 경고는 항상 표시(Q49 A). 최종 문구는 P02 검토 전이라 v1.2 문구를 유지한다(18장).
export const PRIVACY_WARNING = "불필요한 개인정보를 입력하지 마세요."

// S7 판단 유보 화면 문구 (14장 A안). 공식 확인 경로 URL은 S01 확정 전 Mock이다.
export const WITHHELD_COPY = {
  message: "공식 근거를 확인하지 못해 답변을 드리기 어렵습니다.",
  agencies: "확인할 기관: 관할 법원 · 대한법률구조공단",
  link: { title: "공식 확인 경로", url: "https://www.klac.or.kr" },
} as const

export const SSE_STAGE_LABELS = {
  searching: "공식 자료 검색 중",
  lawChecking: "법령 확인 중",
  writing: "답변 작성 · 검증 중",
} as const

export const GUEST_DAILY_LIMIT = 10

const MOCK_SOURCES: SseSource[] = [
  { title: "국가법령정보센터 · 민법 상속편 (Mock)", url: "https://www.law.go.kr" },
  { title: "대법원 전자민원센터 · 상속 안내 (Mock)", url: "https://help.scourt.go.kr" },
  { title: "대한법률구조공단 · 상속 상담 (Mock)", url: "https://www.klac.or.kr" },
]

// 링크 없이 제목만 보여 줄 출처 예시(전화 상담 안내).
const MOCK_NO_URL_SOURCE: SseSource = {
  title: "대한법률구조공단 · 전화 상담 132 (Mock)",
  url: null,
}

const MOCK_ANSWER =
  "상속포기는 일반적으로 상속 개시가 있음을 안 날부터 3개월 안에 가정법원에 신고하는 절차로 안내됩니다. " +
  "기한을 언제부터 셀지는 개인 상황에 따라 달라질 수 있으니 공식 자료로 확인하세요. (Mock 예시 답변)"

const ERROR_MESSAGES: Record<SseErrorEvent["code"], string> = {
  RATE_LIMITED: "오늘 사용할 수 있는 AI 질문 횟수를 모두 사용했습니다.",
  PROVIDER_RATE_LIMIT: "지금은 AI 질문이 많아 잠시 후 다시 시도해 주세요.",
  PROVIDER_UNAVAILABLE: "AI 서비스에 일시적인 문제가 있습니다.",
  PROVIDER_TIMEOUT: "응답 시간이 초과되었습니다.",
}

export const mockErrorMessage = (code: SseErrorEvent["code"]): string => ERROR_MESSAGES[code]

export const encodeSseEvent = ({ event, data }: SseEvent): string =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

const jsonResponse = (status: number, body: ErrorBody): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })

// 서버 422 VALIDATION_ERROR 검사를 흉내 낸다. 입력을 자르거나 고치지 않는다(PRD 3-1-3).
const validateAskRequest = (request: AskAiRequest): string | null => {
  if (!request.question.trim()) return "질문을 입력해 주세요."
  if (countUnicodeCodePoints(request.question) > CHAT_INPUT_POLICY.maxQuestionCodePoints) {
    return `질문은 ${CHAT_INPUT_POLICY.maxQuestionCodePoints}자까지 입력할 수 있습니다.`
  }
  if ((request.previousQuestions?.length ?? 0) > CHAT_INPUT_POLICY.maxPreviousMessages) {
    return "이전 질문은 3개까지 보낼 수 있습니다."
  }
  if (!request.requestId) return "requestId가 필요합니다."
  return null
}

const resultFor = (scenario: MockAiScenario, remainingToday: number | null): SseResultEvent => {
  if (scenario === "withheld") {
    // 출처 0개면 답을 숨긴다 (D-13 A). 오류가 아니라 200 withheld.
    return {
      state: "withheld",
      answer: null,
      sources: [],
      remainingToday,
      reasonCode: "SOURCE_NOT_VERIFIED",
    }
  }
  return {
    state: "answered",
    answer: MOCK_ANSWER,
    sources:
      scenario === "answeredSingleSource"
        ? MOCK_SOURCES.slice(0, 1)
        : scenario === "answeredNoUrlSource"
          ? [MOCK_NO_URL_SOURCE, MOCK_SOURCES[0]]
          : MOCK_SOURCES,
    remainingToday,
    reasonCode: null,
  }
}

// 시나리오별 이벤트 순서. status는 실제 진행 단계만 흉내 낸다.
export const buildMockEvents = (
  scenario: MockAiScenario,
  requestId: string,
  remainingToday: number | null,
): SseEvent[] => {
  const searching: SseEvent = { event: "status", data: { stage: "searching" } }
  const lawChecking: SseEvent = { event: "status", data: { stage: "lawChecking" } }
  const writing: SseEvent = { event: "status", data: { stage: "writing" } }
  const error = (code: SseErrorEvent["code"]): SseEvent => ({
    event: "error",
    data: { code, message: ERROR_MESSAGES[code], requestId },
  })

  switch (scenario) {
    case "providerTimeout":
      return [searching, lawChecking, error("PROVIDER_TIMEOUT")]
    case "providerRateLimit":
      return [searching, error("PROVIDER_RATE_LIMIT")]
    default:
      return [
        searching,
        lawChecking,
        writing,
        { event: "result", data: resultFor(scenario, remainingToday) },
      ]
  }
}

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason)
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer)
        reject(signal.reason)
      },
      { once: true },
    )
  })

export type MockAskOptions = {
  scenario: MockAiScenario
  signal?: AbortSignal
  // 이벤트 사이 지연. 테스트에서는 0으로 둔다.
  stepDelayMs?: number
  // 비로그인 남은 횟수(A10). 로그인 상태면 null.
  remainingToday?: number | null
}

// A08을 흉내 내는 Response를 만든다. 실제 fetch 대신 넣어 use-chat-stream 파서를 시험할 수 있다.
export const createMockAskResponse = async (
  request: AskAiRequest,
  { scenario, signal, stepDelayMs = 600, remainingToday = GUEST_DAILY_LIMIT - 1 }: MockAskOptions,
): Promise<Response> => {
  const invalid = validateAskRequest(request)
  if (invalid) {
    return jsonResponse(422, {
      code: "VALIDATION_ERROR",
      message: invalid,
      requestId: request.requestId,
    })
  }
  // 스트림 시작 전 오류는 HTTP 상태로 돌려준다.
  // 실제 Backend처럼 message에 제한 사유를 넣는다(사람이 읽는 문장이 아니다).
  if (scenario === "guestLimit" || scenario === "memberMinuteLimit") {
    return jsonResponse(429, {
      code: "RATE_LIMITED",
      message:
        scenario === "guestLimit" ? RATE_LIMIT_REASONS.guestDaily : RATE_LIMIT_REASONS.memberMinute,
      requestId: request.requestId,
    })
  }
  if (scenario === "providerUnavailable") {
    return jsonResponse(503, {
      code: "PROVIDER_UNAVAILABLE",
      message: ERROR_MESSAGES.PROVIDER_UNAVAILABLE,
      requestId: request.requestId,
    })
  }

  const events = buildMockEvents(scenario, request.requestId, remainingToday)
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for (const event of events) {
          await wait(stepDelayMs, signal)
          controller.enqueue(encoder.encode(encodeSseEvent(event)))
        }
        controller.close()
      } catch (reason) {
        // 연결을 끊으면 요청이 취소된다(A09 별도 API 없음).
        controller.error(reason)
      }
    },
  })
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  })
}
