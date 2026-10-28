/*
 * 담당: [A] | 책임: 이 기기 저장 기록의 [삭제]와 [저장 동의 철회] 버튼, 확인창, 결과·실패 안내(체크리스트·AI 대화 공용).
 * PRD: 태스크 4-3-1, 4-3-2, 4-3-3, 4-3-4(이 기기 부분). 화면정의서 D-04, 17장 접근성. 정책 P08-B.
 * 구현: 실행 전 확인창에서 무엇을 지우는지와 동의 유지·해제 여부를 구분해 알린다. 성공 응답을 받은 뒤에만 완료 문구를 보인다.
 *   실패하면 완료 문구 없이 남아 있는 기록을 알리고 [다시 시도]를 준다. 결과 안내는 저장 상태가 바뀌어도 남는다.
 * 제한사항: 실제 삭제는 호출자가 넘긴 함수가 한다(shared/storage). 서버 저장 기록 삭제(A17)는 다루지 않는다.
 */
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Notice } from "@/components/ui/notice"

type Action = "delete" | "revoke"
export type StorageActionResult = { action: Action; ok: boolean }

export function StorageControls({
  available,
  itemName,
  deleteLabel,
  revokeLabel,
  onDelete,
  onRevoke,
  result: externalResult,
  onResultChange,
}: {
  // 저장 중일 때만 버튼을 보인다. 결과 안내는 이와 관계없이 남는다.
  available: boolean
  // 지울 기록 이름(예: "체크리스트 기록", "AI 대화 기록")
  itemName: string
  deleteLabel: string
  revokeLabel: string
  onDelete: () => Promise<boolean>
  onRevoke: () => Promise<boolean>
  // 삭제·철회 뒤 화면이 바뀌어도 결과 안내를 남기려면 결과를 바깥에서 보관한다(선택).
  result?: StorageActionResult | null
  onResultChange?: (result: StorageActionResult) => void
}) {
  const [confirming, setConfirming] = useState<Action | null>(null)
  const [busy, setBusy] = useState(false)
  const [internalResult, setInternalResult] = useState<StorageActionResult | null>(null)
  const result = externalResult !== undefined ? externalResult : internalResult
  const setResult = (next: StorageActionResult) => {
    setInternalResult(next)
    onResultChange?.(next)
  }

  // 삭제·철회 함수가 오류를 던져도 실패로 보이고 처리 중 상태에 갇히지 않게 한다.
  const run = async (action: Action) => {
    setConfirming(null)
    setBusy(true)
    let ok = false
    try {
      ok = await (action === "delete" ? onDelete() : onRevoke())
    } catch {
      ok = false
    } finally {
      setBusy(false)
    }
    setResult({ action, ok })
  }

  return (
    <div className="space-y-2">
      {available && (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => setConfirming("delete")}
          >
            {deleteLabel}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => setConfirming("revoke")}
          >
            {revokeLabel}
          </Button>
        </div>
      )}

      {result?.ok && (
        <Notice tone="success">
          {result.action === "delete"
            ? `이 기기의 ${itemName}을 삭제했습니다. 저장 동의는 유지됩니다.`
            : `저장 동의를 철회하고 이 기기의 ${itemName}을 삭제했습니다.`}
        </Notice>
      )}
      {result && !result.ok && (
        <Notice tone="danger" className="space-y-2">
          <p>
            {result.action === "delete" ? "삭제하지 못했습니다." : "동의를 철회하지 못했습니다."} 이
            기기의 {itemName}이 그대로 남아 있고 저장 동의도 바뀌지 않았습니다.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void run(result.action)}
          >
            다시 시도
          </Button>
        </Notice>
      )}

      {confirming && (
        <ConfirmDialog
          title={confirming === "delete" ? `${itemName}을 삭제할까요?` : "저장 동의를 철회할까요?"}
          actions={[
            {
              label: confirming === "delete" ? `삭제: ${itemName}` : `동의 철회: ${itemName} 삭제`,
              primary: true,
              onClick: () => void run(confirming),
            },
          ]}
          onCancel={() => setConfirming(null)}
        >
          <p className="text-sm text-muted-foreground">
            {confirming === "delete"
              ? `이 기기에 저장한 ${itemName}만 지웁니다. 저장 동의는 유지되어 이후 내용은 다시 저장됩니다.`
              : `이 기기의 ${itemName}을 지우고 저장 동의를 해제합니다. 다시 동의하기 전에는 저장하지 않습니다.`}
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
