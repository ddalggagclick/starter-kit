/*
 * 담당: [A] | 책임: 앱 레이아웃에서 체크리스트 저장·복원을 시작하고 화면을 떠나면 멈춘다.
 * PRD: 태스크 4-2-1, 4-2-3. W-02뿐 아니라 W-04에서 바꾼 '안내 확인'도 저장되도록 레이아웃에서 시작한다.
 * 제한사항: namespace는 지금 Guest 고정이다. 로그인 계정 전환(4-2-2)은 인증 이슈에서 인자로 넘긴다.
 */
import { useEffect } from "react"
import { GUEST_NAMESPACE, inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
import { startChecklistPersistence } from "./checklist-storage"

export const useChecklistPersistence = (namespace: StorageNamespace = GUEST_NAMESPACE) => {
  useEffect(() => {
    const persistence = startChecklistPersistence(inheritanceDb, namespace)
    return persistence.stop
  }, [namespace])
}
