/*
 * 담당: [A] | 책임: W-02의 [체크리스트 삭제]·[체크리스트 저장 동의 철회]와 결과 안내.
 * PRD: 태스크 4-3-1, 4-3-2, 4-3-3, 4-3-4(이 기기 부분). 화면정의서 D-04.
 * 구현: 저장 중일 때만 버튼을 보인다. 결과는 저장 상태 스토어에 보관해, 삭제·철회로 체크리스트 화면이 바뀌어도 안내가 남는다.
 *   삭제·철회와 결과·재시도는 요청한 계정(namespace)에 고정한다. 계정이 바뀌면 이전 계정의 결과·확인창·재시도를 보이지 않는다.
 */
import { StorageControls } from "@/components/ui/storage-controls"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { DELETE_BUTTON_LABELS } from "@/mocks/checklist"
import {
  deleteChecklistRecords,
  revokeChecklistStorage,
  useChecklistStorageStore,
} from "./checklist-storage"

export function ChecklistStorageControls() {
  const namespace = useAuthStore(selectNamespace)
  const status = useChecklistStorageStore((s) => s.status)
  const lastAction = useChecklistStorageStore((s) => s.lastAction)
  return (
    <StorageControls
      // 계정이 바뀌면 새로 그려 열려 있던 확인창 등 이전 계정의 화면 상태를 버린다.
      key={namespace}
      available={status === "ready"}
      itemName="체크리스트 기록"
      deleteLabel={DELETE_BUTTON_LABELS.checklist}
      revokeLabel="체크리스트 저장 동의 철회"
      onDelete={() => deleteChecklistRecords(namespace)}
      onRevoke={() => revokeChecklistStorage(namespace)}
      result={lastAction?.namespace === namespace ? lastAction : null}
      onResultChange={(result) =>
        useChecklistStorageStore.setState({ lastAction: { ...result, namespace } })
      }
    />
  )
}
