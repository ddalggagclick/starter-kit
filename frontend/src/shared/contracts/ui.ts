/*
 * 담당: [A] | 책임: K/W/S 화면 상태 상수
 * 구현할 기능: 화면 ID·채팅 S1~S9·저장 동의 상태 정의; S5 미사용 및 200코드포인트/3발화/0회 정책 동기화
 * 코드 경계: 로컬 화면/도메인 타입이다. HTTP 계약은 생성된 OpenAPI 타입을 따른다.
 * 완료 기준: 정상/실패/취소/재진입 상태를 UI 테스트로 확인.
 * 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
 */
export type ScreenId =
  | "K-01"
  | "K-02"
  | "K-03"
  | "K-04"
  | "W-00"
  | "W-01"
  | "W-02"
  | "W-03"
  | "W-04"
  | "W-05"
  | "W-06"
  | "W-07"
  | "W-08"

export type ChatScreenState = "S1" | "S2" | "S3" | "S4" | "S5" | "S6" | "S7" | "S8" | "S9"

// T5 승인값. JS string.length는 UTF-16 코드 유닛이므로 코드 포인트 계산에 사용 금지.
export const CHAT_INPUT_POLICY = {
  maxQuestionCodePoints: 200,
  maxPreviousMessages: 3,
  maxClarificationQuestions: 0,
} as const

export const countUnicodeCodePoints = (value: string): number => Array.from(value).length
// S5는 최신 화면정의서 식별자 호환성 용도로만 유지; AI가 추가 질문하는 전이는 사용하지 않는다.
export type StorageConsentScope = "checklist" | "chat"
export type StorageStatus = "not-consented" | "ready" | "failed"
// HTTP 요청/응답 필드 및 SSE 이벤트 페이로드는 API 담당자 OpenAPI 확정 후 생성합니다.
