/*
 * 담당: [A] | 책임: 앱 시작 시 Refresh 쿠키로 로그인 상태를 조용히 복구한다(새로고침 후 유지).
 * PRD: E5 / 스토리 5-3. Mock 모드에서는 복구하지 않는다(Mock 로그인은 새로고침하면 사라짐).
 * 제한사항: 실패하면 비로그인으로 둔다. 결과가 오기 전에 사용자가 직접 로그인했으면 덮어쓰지 않는다.
 */
import { useEffect } from "react"
import { restoreSessionRequest } from "./auth-api"
import { useAuthStore } from "./auth-store"

export const useSessionRestore = () => {
  useEffect(() => {
    let active = true
    void restoreSessionRequest().then((account) => {
      if (active && account && !useAuthStore.getState().accountId) {
        useAuthStore.getState().signIn(account)
      }
    })
    return () => {
      active = false
    }
  }, [])
}
