/*
 * 담당: [A] | 책임: 화면이 쓰는 A07 절차 목록·상세 타입(백엔드 응답을 features/procedures/api.ts에서 정규화한 모양).
 * 근거: docs/contracts/openapi.yaml A07(x-confirmed: true). 생성 타입(shared/api/schema.d.ts)은 모든 필드가 선택이라,
 *   빈 값을 채운 뒤의 모양을 여기 둔다. 2026-10-27 mocks/wire-types.ts에서 옮겼다.
 */
import type { ProcedureId } from "./domain"

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
