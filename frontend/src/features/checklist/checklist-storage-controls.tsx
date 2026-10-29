/*
 * 담당: [A] | 책임: W-02의 [체크리스트 삭제]·[체크리스트 저장 동의 철회]와 결과 안내.
 * PRD: 태스크 4-3-1, 4-3-2, 4-3-3, 4-3-4(이 기기 부분). 화면정의서 D-04.
 * 구현: 저장 중일 때만 버튼을 보인다. 결과는 저장 상태 스토어에 보관해, 삭제·철회로 체크리스트 화면이 바뀌어도 안내가 남는다.
 *   삭제·철회와 결과·재시도는 요청한 계정(namespace)에 고정한다. 계정이 바뀌면 이전 계정의 결과·확인창·재시도를 보이지 않는다.
 *   #227 최신 시안: 체크리스트 화면은 useChecklistStorageActions로 [삭제]는 목록 아래 링크, [동의 철회]는 [저장] 모달 안에서 부른다.
 */
import { StorageControls, useStorageActions } from "@/components/ui/storage-controls"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { DELETE_BUTTON_LABELS } from "@/shared/content/checklist"
import {
  deleteChecklistRecords,
  revokeChecklistStorage,
  useChecklistStorageStore,
} from "./checklist-storage"

const useChecklistStorageOptions = () => {
  const namespace = useAuthStore(selectNamespace)
  const lastAction = useChecklistStorageStore((s) => s.lastAction)
  return {
    namespace,
    itemName: "체크리스트 기록",
    // 시안 확인창 제목
    deleteTitle: "체크리스트를 삭제할까요?",
    revokeTitle: "체크리스트 저장 동의를 철회할까요?",
    onDelete: () => deleteChecklistRecords(namespace),
    onRevoke: () => revokeChecklistStorage(namespace),
    result: lastAction?.namespace === namespace ? lastAction : null,
    onResultChange: (result: { action: "delete" | "revoke"; ok: boolean }) =>
      useChecklistStorageStore.setState({ lastAction: { ...result, namespace } }),
  }
}

// 버튼 없이 삭제·철회 요청(request)과 확인창·결과 안내(view)만 준다. available = 저장 중인지.
export function useChecklistStorageActions() {
  const status = useChecklistStorageStore((s) => s.status)
  const { namespace: _namespace, ...options } = useChecklistStorageOptions()
  const actions = useStorageActions(options)
  return { ...actions, available: status === "ready" }
}

export function ChecklistStorageControls() {
  const status = useChecklistStorageStore((s) => s.status)
  const { namespace, ...options } = useChecklistStorageOptions()
  return (
    <StorageControls
      // 계정이 바뀌면 새로 그려 열려 있던 확인창 등 이전 계정의 화면 상태를 버린다.
      key={namespace}
      available={status === "ready"}
      deleteLabel={DELETE_BUTTON_LABELS.checklist}
      revokeLabel="체크리스트 저장 동의 철회"
      {...options}
    />
  )
}
