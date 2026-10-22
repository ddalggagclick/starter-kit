/*
 * 담당: [A] | 책임: V1 화면이 실제 Backend와 Mock 중 어디에서 데이터를 받는지 한 곳에서 정한다.
 * PRD: 간트 14(V1 모의 흐름), 태스크 2-1-4·3-1-5(실구현 시연으로 표기 금지).
 * 구현: VITE_USE_MOCK_API가 "false"일 때만 실제 Backend를 쓴다. 기본값은 Mock이다.
 *   실제 Backend에 라우터가 있는 API는 A05 Handoff 교환뿐이다(2026-10-22 확인). 나머지(A07 절차, A08 AI,
 *   A13 로그인)는 Backend 라우터가 없어 항상 Mock이며, 화면에 'Mock' 표시를 남긴다.
 * 제한사항: Mock 응답을 실제 연동 결과로 보고하지 않는다.
 */
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== "false"

// shared/api/client.ts는 VITE_API_BASE_URL이 없으면 import 시점에 예외를 던진다.
// Mock만 쓰는 테스트·화면에서 그 예외를 피하려고 실제 호출 때만 불러온다.
export const loadApiClient = async () => (await import("./client")).api
