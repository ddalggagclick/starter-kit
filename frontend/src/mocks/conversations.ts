/*
 * 담당: [A] | 책임: W-07 S10 이전 대화 목록 Mock (AI 대화 저장 동의 상태에서만 진입).
 * 근거: 화면정의서 v1.4 08장 S10, 부록4, D-04·D-05·D-14.
 * 제한사항: 실제 Dexie 저장이 아니다. 대화 목록 상한·제목 길이는 검증 필요(P02)라 Mock 값이다.
 */
import type { SseResultEvent } from "./wire-types"

export type MockChatTurn = { question: string; result: SseResultEvent }

export type MockConversation = {
  conversationId: string
  // 날짜 라벨. 저장 시각 형식은 Dexie 스키마 결정 전이다.
  dateLabel: string
  turns: MockChatTurn[]
}

// 제목 = 첫 질문 앞부분 (D-14). 글자 수는 미정이라 Mock 값 20을 쓴다.
export const MOCK_TITLE_MAX_CODE_POINTS = 20
export const conversationTitle = (conversation: MockConversation): string => {
  const first = Array.from(conversation.turns[0]?.question ?? "")
  return first.length > MOCK_TITLE_MAX_CODE_POINTS
    ? `${first.slice(0, MOCK_TITLE_MAX_CODE_POINTS).join("")}…`
    : first.join("")
}

export const MOCK_CONVERSATIONS: MockConversation[] = [
  {
    conversationId: "mock-conv-1014",
    dateLabel: "10/14",
    turns: [
      {
        question: "상속포기 기한이 언제부터인가요?",
        result: {
          state: "answered",
          answer:
            "상속포기는 일반적으로 상속 개시가 있음을 안 날부터 3개월 안에 신고하는 절차로 안내됩니다[1]. 개인 상황은 공식 자료로 확인하세요[2]. (Mock 예시 답변)",
          sources: [
            { title: "국가법령정보센터 · 민법 상속편 (Mock)", url: "https://www.law.go.kr" },
            { title: "대법원 전자민원센터 · 상속 안내 (Mock)", url: "https://help.scourt.go.kr" },
          ],
          remainingToday: null,
          reasonCode: null,
        },
      },
    ],
  },
  {
    conversationId: "mock-conv-1012",
    dateLabel: "10/12",
    turns: [
      {
        question: "안심상속 신청은 어디서 하나요?",
        result: {
          state: "answered",
          answer:
            "안심상속 원스톱 서비스는 주민센터 방문 또는 정부24에서 신청 방법을 확인할 수 있습니다[1]. (Mock 예시 답변)",
          sources: [{ title: "정부24 · 안심상속 원스톱 서비스 (Mock)", url: "https://www.gov.kr" }],
          remainingToday: null,
          reasonCode: null,
        },
      },
    ],
  },
]

export const EMPTY_CONVERSATIONS_COPY = "저장된 대화가 없습니다"

// S11 이탈 확인 (D-11). 저장 불가 상태면 저장 버튼을 숨긴다.
export const LEAVE_CONFIRM_COPY = {
  message: "이 대화는 저장되지 않아 나가면 사라집니다.",
  saveAndLeave: "이 기기에 저장하고 이동",
  leaveWithoutSave: "저장 없이 이동",
  cancel: "취소",
} as const

// S8 새 대화 — 저장 중이면 확인 없이 보관 후 새 대화 (15장 ② A안)
export const NEW_CHAT_ARCHIVED_COPY = "저장 중: 지금 대화는 이전 대화로 보관됩니다"
