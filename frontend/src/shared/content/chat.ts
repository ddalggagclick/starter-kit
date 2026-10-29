/*
 * 담당: [A] | 책임: W-07 AI 질문 화면의 실제 안내 문구(예시 질문·개인정보 경고·판단 유보·진행 단계·하루 한도).
 * 근거: 화면정의서 v1.4 08·14·18장, 결정 Q49. 실제 화면과 Mock(mocks/ai-stream.ts)이 함께 쓴다.
 * 이동: 2026-10-27 mocks/ai-stream.ts에서 옮겼다(실제 화면 문구를 Mock과 분리). 문구는 바꾸지 않았다.
 */

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

// #227 새 시안: 대화창 위쪽 줄의 짧은 저장 상태 표시. 긴 문장 대신 기호(○ ✓ ⚠)와 두세 단어로 보인다.
//   화면낭독기에는 앞에 "AI 대화"를 붙여 읽힌다(chat-history.tsx). checking은 저장소를 여는 중인 잠깐의 상태다.
export const CHAT_SAVE_BADGE_LABELS = {
  checking: "저장 확인 중",
  "not-consented": "저장 안 됨",
  ready: "저장 중",
  failed: "저장할 수 없음",
} as const
