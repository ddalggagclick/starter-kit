/*
 * 담당: [A] | 책임: Mock 전용 HTTP wire 타입.
 * 근거: docs/contracts/openapi.yaml 0.2.0-draft (2026-10-21). 필드 이름·enum을 그대로 옮겼다.
 * 제한사항: 승인된 생성 타입(shared/api/schema.d.ts)을 대신하지 않는다. Mock 밖에서 import하지 않는다.
 *   API 담당자 승인 후 openapi-typescript 생성 타입으로 교체한다.
 */
import type { AnswerChoice, ProcedureId, Relationship, RiskId } from "@/shared/contracts/domain"

// components/schemas/Error — code는 core/errors.py 기준
export type ErrorBody = { code: string; message: string; requestId?: string }

// A04·A05 HandoffPayload. deathDate가 null이면 deathDateUnknown은 true여야 한다(불일치는 422).
export type HandoffPayload = {
  relationship: Relationship
  deathDate: string | null
  deathDateUnknown: boolean
  oneStopApplication: AnswerChoice
  // 답한 위험 질문만 포함
  risks?: { riskId: RiskId; answer: AnswerChoice }[]
}

// A07 목록 (openapi 0.2.1 x-confirmed: true)
export type ProcedureSummary = { procedureId: ProcedureId; name: string; summary: string }
export type ProcedureListResponse = { procedures: ProcedureSummary[] }

export type OfficialLink = { title: string; url: string }

// A07 상세. 이름(name)은 상세 스키마에 없어 목록의 name과 합쳐 표시한다.
export type ProcedureDetail = {
  procedureId: ProcedureId
  action: string
  deadline: string
  risk: string
  agency: string
  documents: string[]
  methods: string[]
  exceptions: string[]
  contacts: string[]
  officialLinks: OfficialLink[]
  // 0~3개. 필드 이름·저장 위치는 D4 보류
  relatedProcedureIds: ProcedureId[]
}

// A08 요청
export type AskAiRequest = {
  question: string
  requestId: string
  previousQuestions?: string[]
}

// A08 SSE 이벤트 (event: status → result 또는 error)
export type SseStage = "searching" | "lawChecking" | "writing"
export type SseStatusEvent = { stage: SseStage }
// url이 null이면 링크 없는 출처(전화 상담·공식 사이트 안내 등)다. 백엔드 #103 기준, openapi는 아직 null 불가로 적혀 있다.
export type SseSource = { title: string; url: string | null }
export type SseResultEvent = {
  state: "answered" | "withheld"
  answer: string | null
  sources: SseSource[]
  remainingToday: number | null
  reasonCode: "SOURCE_NOT_VERIFIED" | "CITATION_MISMATCH" | null
}
export type SseErrorCode =
  | "RATE_LIMITED"
  | "PROVIDER_RATE_LIMIT"
  | "PROVIDER_UNAVAILABLE"
  | "PROVIDER_TIMEOUT"
export type SseErrorEvent = { code: SseErrorCode; message: string; requestId?: string }

export type SseEvent =
  | { event: "status"; data: SseStatusEvent }
  | { event: "result"; data: SseResultEvent }
  | { event: "error"; data: SseErrorEvent }

// A13 로그인. Refresh는 HttpOnly 쿠키로 별도 전달된다.
export type LoginResponse = { accessToken: string; expiresIn: number }

// A17 (x-status: 제안). itemStates 항목 구조는 미정이다.
export type ChecklistSaved = { itemStates: object[]; serverSaveConsent: boolean }
