/*
 * 담당: [A] | 책임: W-07 세션 메모리 상태(외부 전송 안내 확인 여부, 비로그인 남은 질문 수).
 * PRD: 태스크 3-1-2(최초 외부 전송 안내), 5-6-2·3-7-1(비로그인 하루 10회).
 * 구현: Zustand 메모리. 새로고침하면 처음으로 돌아간다. 남은 횟수는 서버 result.remainingToday를 따른다.
 *   실제 A08은 횟수 저장 방식(A10) 결정 전이라 remainingToday가 null이다. 모르면 null로 두고 숫자를 지어내지 않는다.
 * 제한사항: 실제 하루 제한 계산은 서버(A10) 책임이다. 대화 원문은 여기에 저장하지 않는다.
 */
import { create } from "zustand"
import { GUEST_DAILY_LIMIT } from "@/mocks/ai-stream"
import { USE_MOCK_API } from "@/shared/api/data-source"

type ChatSessionState = {
  externalNoticeAcknowledged: boolean
  guestRemaining: number | null
  acknowledgeExternalNotice: () => void
  setGuestRemaining: (value: number | null) => void
}

export const useChatSessionStore = create<ChatSessionState>()((set) => ({
  externalNoticeAcknowledged: false,
  guestRemaining: USE_MOCK_API ? GUEST_DAILY_LIMIT : null,
  acknowledgeExternalNotice: () => set({ externalNoticeAcknowledged: true }),
  setGuestRemaining: (value) => set({ guestRemaining: value }),
}))
