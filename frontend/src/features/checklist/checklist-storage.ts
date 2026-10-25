/*
 * 담당: [A] | 책임: W-02 체크리스트의 저장 동의 상태와 IndexedDB 저장·복원 연결.
 * PRD: E4 / 태스크 4-2-1, 2-5-3, 4-1-2, 4-2-3, 4-2-4, 2-4-3, 2-4-4. 화면정의서 D-02·D-09·D-10·D-12. 정책 S04-A·S10-A.
 * 구현: 시작할 때 동의를 확인해 동의했으면 같은 namespace 기록을 복원한다. 동의 상태에서는 체크리스트(Zustand)가
 *   바뀔 때마다 순서대로 저장한다. 동의하는 순간 현재 메모리 상태를 바로 저장한다.
 * 완료 기준: 미동의면 IndexedDB 기록 0건, 저장 성공 전에는 '저장 중'을 표시하지 않고, 실패해도 메모리 이용은 계속된다.
 * 제한사항: 저장은 shared/storage의 동의 확인 함수로만 한다(Dexie 테이블 직접 조작 금지).
 *   계정별 namespace 전환(4-2-2)은 인증 이슈에서 namespace 인자로 연결한다. 삭제·철회 UI(4-3)는 후속 이슈다.
 *   저장 기록과 새 카카오 응답이 충돌할 때의 선택 UI(T06-B)는 없다. 메모리에 답이 있으면 복원하지 않는다.
 */
import { create } from "zustand"
import type { StorageStatus } from "@/shared/contracts/ui"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import {
  grantConsent,
  loadConsentStatuses,
  saveChecklistWithConsent,
} from "@/shared/storage/consent"
import {
  type ChecklistSnapshot,
  GUEST_NAMESPACE,
  type InheritanceDb,
  loadChecklist,
  type StorageNamespace,
} from "@/shared/storage/db"

// checking: 시작 시 동의·기록을 읽는 중. 이때는 동의 버튼을 보이지 않는다.
export type ChecklistStorageStatus = StorageStatus | "checking"

type ChecklistStorageState = {
  namespace: StorageNamespace
  status: ChecklistStorageStatus
  // [저장 안 함]을 누르면 이번 방문 동안 동의 띠를 접는다. 저장하지 않으므로 다음 방문에 다시 묻는다.
  declined: boolean
}

export const useChecklistStorageStore = create<ChecklistStorageState>()(() => ({
  namespace: GUEST_NAMESPACE,
  status: "checking",
  declined: false,
}))

const setStatus = (status: ChecklistStorageStatus) => useChecklistStorageStore.setState({ status })

const snapshotOf = (): ChecklistSnapshot | null => {
  const { answers, riskAnswers, procedureStates } = useInheritanceStore.getState()
  return answers ? { answers, riskAnswers, procedureStates } : null
}

// 실패 사유가 동의 없음이면 미동의로, 그 밖이면 저장 불가로 표시한다.
const statusAfterFailure = (reason: string): ChecklistStorageStatus =>
  reason === "not-consented" ? "not-consented" : "failed"

export type ChecklistPersistence = {
  // 시작 시 동의 확인·복원이 끝나면 풀린다.
  ready: Promise<void>
  // 대기 중인 저장이 모두 끝나면 풀린다(테스트·화면 이탈 전 확인용).
  flush: () => Promise<void>
  stop: () => void
}

// 앱 레이아웃에서 한 번 시작한다. namespace가 바뀌면 stop 후 다시 시작한다.
export const startChecklistPersistence = (
  db: InheritanceDb,
  namespace: StorageNamespace,
): ChecklistPersistence => {
  let active = true
  let queue: Promise<void> = Promise.resolve()
  useChecklistStorageStore.setState({ namespace, status: "checking", declined: false })

  // 저장은 이전 저장이 끝난 뒤 최신 상태로 한다. 늦게 끝난 오래된 저장이 새 상태를 덮지 않게 한다.
  const save = () => {
    queue = queue.then(async () => {
      const snapshot = snapshotOf()
      if (!active || !snapshot) return
      const result = await saveChecklistWithConsent(db, namespace, snapshot)
      if (active && !result.ok) setStatus(statusAfterFailure(result.reason))
    })
    return queue
  }

  const unsubscribe = useInheritanceStore.subscribe((state, previous) => {
    if (useChecklistStorageStore.getState().status !== "ready") return
    const changed =
      state.answers !== previous.answers ||
      state.riskAnswers !== previous.riskAnswers ||
      state.procedureStates !== previous.procedureStates
    if (changed) void save()
  })

  const ready = (async () => {
    const statuses = await loadConsentStatuses(db, namespace)
    if (!active) return
    if (statuses.checklist !== "ready") {
      setStatus(statuses.checklist)
      return
    }
    const loaded = await loadChecklist(db, namespace)
    if (!active) return
    if (!loaded.ok) {
      setStatus("failed")
      return
    }
    if (loaded.value) useInheritanceStore.getState().restoreSaved(loaded.value)
    setStatus("ready")
  })()

  return {
    ready,
    flush: () => queue,
    stop: () => {
      active = false
      unsubscribe()
    },
  }
}

// 사용자가 정책을 확인하고 체크한 뒤 [저장]을 눌렀을 때만 호출한다(P01-C, 4-1-2).
// 동의를 기록하고 지금 화면의 답을 바로 저장한다. 저장에 성공해야 '저장 중'이 된다(D-10).
export const grantChecklistStorage = async (db: InheritanceDb): Promise<void> => {
  const { namespace } = useChecklistStorageStore.getState()
  const granted = await grantConsent(db, namespace, "checklist")
  if (!granted.ok) {
    setStatus("failed")
    return
  }
  const snapshot = snapshotOf()
  if (snapshot) {
    const saved = await saveChecklistWithConsent(db, namespace, snapshot)
    if (!saved.ok) {
      setStatus(statusAfterFailure(saved.reason))
      return
    }
  }
  setStatus("ready")
}

export const declineChecklistStorage = () => useChecklistStorageStore.setState({ declined: true })
