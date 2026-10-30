/*
 * 담당: [A] | 책임: 화면에 떠 있는 AI 대화창의 저장 상태·동작을 플로팅 [저장] 모달에 잇는 연결 통로(메모리).
 * 근거: 사용자 지시(2026-10-30) "저장은 저장 네비게이팅에서만" — 대화창 위쪽 줄의 저장 설정을 빼고 저장 모달로 옮겼다.
 * 구현: 대화창(HomeChatScreen)이 그려질 때 자기 상태(status·declined)와 동작(grant·decline·revoke)을 올리고,
 *   사라지면 지운다. 저장 모달은 이 값만 읽어 그린다 — 대화창의 실제 저장 동작(지금 대화 함께 저장 등)을 그대로 쓴다.
 * 제한사항: 대화창이 없는 화면(첫 화면)에서는 비어 있어 AI 대화 저장 칸을 보이지 않는다. 대화 내용은 담지 않는다.
 */
import { create } from "zustand"
import type { ChatStorageStatus } from "./chat-storage"

export type ChatStorageBridge = {
  status: ChatStorageStatus
  declined: boolean
  grant: () => Promise<boolean>
  decline: () => void
  // 저장 설정 창에서 철회할 때: 대화창의 실제 철회(지금 대화 비우기 + 기록 삭제)를 바로 실행한다.
  revoke: () => Promise<boolean>
}

export const useChatStorageBridge = create<{
  current: ChatStorageBridge | null
  set: (bridge: ChatStorageBridge | null) => void
}>((set) => ({
  current: null,
  set: (bridge) => set({ current: bridge }),
}))
