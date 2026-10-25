/*
 * 담당: [A] | 책임: 헤더·AI 화면·저장 영역이 보는 로그인 상태(메모리).
 * PRD: E5 / 태스크 5-2-1(로그인 상태 전환), 5-3-3(Refresh 실패 시 해제), 5-6-1, 4-2-2(계정별 저장 영역).
 * 구현: 로그인하면 계정 ID와 이메일을 메모리에 둔다. Refresh가 실패하면 자동으로 로그아웃 상태가 된다.
 *   이 기기 저장 영역(namespace)은 계정 ID로 정한다. 비로그인은 Guest다.
 * 제한사항: Access Token은 shared/api/auth.ts의 메모리 세션에만 있다. 이 스토어와 브라우저 저장소에 토큰을 두지 않는다.
 */
import { create } from "zustand"
import { setAuthLostListener } from "@/shared/api/auth"
import { accountNamespace, GUEST_NAMESPACE, type StorageNamespace } from "@/shared/storage/db"
import type { SignedInAccount } from "./auth-api"

type AuthState = {
  accountId: string | null
  // 세션 복구(새로고침)로 로그인한 경우 이메일을 모른다(A21 미확정).
  email: string | null
  signIn: (account: SignedInAccount) => void
  signOut: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  accountId: null,
  email: null,
  signIn: ({ accountId, email }) => set({ accountId, email }),
  signOut: () => set({ accountId: null, email: null }),
}))

export const selectNamespace = (state: Pick<AuthState, "accountId">): StorageNamespace =>
  state.accountId ? accountNamespace(state.accountId) : GUEST_NAMESPACE

// Refresh 실패(만료·재사용 탐지)로 인증이 끊기면 계정 화면을 숨긴다(5-3-3).
setAuthLostListener(() => useAuthStore.getState().signOut())
