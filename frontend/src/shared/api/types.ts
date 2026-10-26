/*
 * 담당: [A] | 책임: OpenAPI 생성 타입(schema.d.ts)에서 화면이 쓰는 wire 타입 이름을 꺼낸다.
 * PRD: E7 / 스토리 7-1 / 태스크 7-1-3.
 * 근거: docs/contracts/openapi.yaml 0.2.0-draft (2026-10-21). `npm run api:types`로 schema.d.ts를 다시 만든다.
 * 완료 기준: REST JSON camelCase 필드가 생성 타입과 일치한다. 손으로 쓴 DTO를 따로 두지 않는다.
 * 제한사항: x-confirmed: false 또는 x-path-proposed 항목(A07 절차, A05 경로 등)은 API 담당자 승인 전이다.
 */
import type { components } from "./schema"

type Schemas = components["schemas"]

export type ApiErrorBody = Schemas["Error"]
export type HandoffPayload = Schemas["HandoffPayload"]
export type ProcedureDetailWire = Schemas["ProcedureDetail"]
export type SseStatusEvent = Schemas["SseStatusEvent"]
export type SseResultEvent = Schemas["SseResultEvent"]
export type SseErrorEvent = Schemas["SseErrorEvent"]
export type SseSource = Schemas["SseSource"]

// A08 429 RATE_LIMITED(스트림 시작 전)의 message로 제한 사유를 구분한다(3-7-3).
// Backend #138(비회원 하루 10회)·#143(로그인 사용자 1분 10회), API 담당자 확인(2026-10-26).
// 실제 화면과 Mock이 함께 쓰는 wire 값이라 Mock 파일이 아니라 여기에 둔다(리뷰 반영).
// openapi에 아직 없어 생성 타입에서 꺼낼 수 없다. openapi에 반영되면 생성 타입으로 바꾼다.
export const RATE_LIMIT_REASONS = {
  guestDaily: "GUEST_DAILY_LIMIT",
  memberMinute: "MEMBER_MINUTE_LIMIT",
} as const
