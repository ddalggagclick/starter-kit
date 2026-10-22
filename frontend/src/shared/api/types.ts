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
