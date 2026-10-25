/*
 * 담당: [A] | 책임: 앱 레이아웃에서 체크리스트 저장·복원을 시작하고, 로그인 계정이 바뀌면 저장 영역을 바꾼다.
 * PRD: 태스크 4-2-1, 4-2-3, 4-2-2(계정별 저장 영역), 5-3-3(인증 해제 시 계정 기록 숨김).
 *   W-02뿐 아니라 W-04에서 바꾼 '안내 확인'도 저장되도록 레이아웃에서 시작한다.
 * 구현: 저장 영역(namespace)은 로그인 상태에서 정한다(Guest / account:<id>). 바뀌면 ① 이전 영역 자동 저장 정지
 *   → ② 화면 메모리 비우기 → ③ 새 영역 시작·복원 순서로 처리한다. 이 순서라야 이전 계정 화면이 새 계정 영역에 저장되지 않는다.
 * 제한사항: 로그아웃은 기록을 지우지 않고 화면에서만 숨긴다(S05-D). 비로그인 기록을 계정으로 옮기거나
 *   합치지 않는다(자동 병합 금지 S06-B, T08-B의 명시 확인 UI는 미구현).
 */
import { useEffect, useRef } from "react"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { type InheritanceDb, inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
import { startChecklistPersistence } from "./checklist-storage"

export const useChecklistPersistence = (db: InheritanceDb = inheritanceDb) => {
  const namespace = useAuthStore(selectNamespace)
  const previous = useRef<StorageNamespace | null>(null)

  useEffect(() => {
    // 이전 영역의 정지(cleanup)는 이 effect보다 먼저 실행된다(①). 그 뒤에 메모리를 비운다(②).
    if (previous.current !== null && previous.current !== namespace) {
      useInheritanceStore.getState().reset()
    }
    previous.current = namespace
    const persistence = startChecklistPersistence(db, namespace) // ③
    return persistence.stop
  }, [db, namespace])
}
