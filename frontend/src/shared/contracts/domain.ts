/*
 * 담당: [A] | 책임: 프론트 내부 선택값 타입
 * 구현할 기능: 백엔드 초기/위험/절차 enum과 동기화; HTTP 타입과 분리
 * 코드 경계: 로컬 화면/도메인 타입이다. HTTP 계약은 생성된 OpenAPI 타입을 따른다.
 * 완료 기준: 정상/실패/취소/재진입 상태를 UI 테스트로 확인.
 * 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
 */
export type AnswerChoice = "yes" | "no" | "unknown"
export type Relationship = "spouse" | "descendant" | "ascendant" | "sibling" | "other" | "unknown"
export type RiskId = "debt" | "property_disposal" | "self_application"
export type ProcedureId = "p01" | "p02" | "p03" | "p04" | "p05" | "p06" | "p07" | "p08"
export type InitialAnswers = {
  relationship: Relationship
  deathDate: string | null
  deathDateUnknown: boolean
  oneStopApplication: AnswerChoice
}
export type RiskAnswer = { riskId: RiskId; answer: AnswerChoice; confirmed: boolean }
