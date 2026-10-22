/*
 * 담당: [A] | 책임: 헤더·AI 화면이 보는 로그인 상태(메모리).
 * PRD: E5 / 태스크 5-2-1(로그인 상태 전환), 5-6-1.
 * 구현: 로그인 성공 시 이메일만 메모리에 둔다. 새로고침하면 비로그인으로 돌아간다.
 * 제한사항: V1 로그인은 Mock(A13 라우터 없음)이다. Access Token을 브라우저 저장소에 쓰지 않고,
 *   Mock 토큰은 공통 Axios 세션(accessSession)에도 넣지 않는다(실제 Backend로 새지 않게).
 */
import { create } from "zustand"

type AuthState = {
  email: string | null
  signIn: (email: string) => void
  signOut: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  email: null,
  signIn: (email) => set({ email }),
  signOut: () => set({ email: null }),
}))
