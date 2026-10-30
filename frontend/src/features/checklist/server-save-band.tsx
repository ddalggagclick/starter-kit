/*
 * 담당: [A] | 책임: W-02 로그인 사용자의 서버(계정) 체크리스트 저장 동의·상태·불러오기·철회 띠.
 * PRD: 태스크 4-5-1, 4-6-1, 4-5-3, 4-6-3, 4-3-4(서버). 화면정의서 D-03, 17장 접근성(문구·기호 병기, 확인창).
 * 구현: 이 기기 저장 동의와 따로 받는다(정책 확인 + 명시 체크). 서버 기록이 있으면 자동으로 합치지 않고 사용자가 고른다.
 *   #197(현주 님 UI 제안·디자인 시스템 7.4): 화면에는 상태 한 줄과 버튼만 두고, 동의는 [서버 저장 설정]을 누르면 모달로 묻는다.
 *   로그인 후 서버 기록이 있으면 고르는 모달이 한 번 저절로 열린다. 닫으면(나중에 고르기) [선택하기]로 다시 연다.
 *   고르면(불러오기·덮어쓰기·저장) 상태가 바뀌어 모달이 저절로 닫힌다.
 *   서버 철회가 실패하면 서버에 기록이 남았다고 알리고 서버만 다시 시도한다. 모든 동작은 지금 로그인 계정에 고정한다.
 *   답이 없는 화면(질문 전·이 기기 기록 삭제 뒤)에도 놓인다: 동의 요청과 덮어쓰기는 숨기고,
 *   서버 기록 불러오기·서버 철회·실패 재시도는 그대로 보인다(리뷰 반영, 검증 ②).
 * 제한사항: A17은 계약 미확정·Backend 미구현이다. Mock 모드에서는 실제 서버 연동이 아님을 표시한다. 정책 문구는 P02 검토 전 초안.
 */
import { Settings2 } from "lucide-react"
import { useId, useState } from "react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Modal } from "@/components/ui/modal"
import { Notice } from "@/components/ui/notice"
import { useAuthStore } from "@/features/auth/auth-store"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import type { ChecklistSnapshot } from "@/shared/storage/db"
import {
  declineServerSave,
  grantServerSave,
  keepLocalOverServer,
  loadServerRecord,
  recheckServerSave,
  retryServerSave,
  revokeServerSave,
  useServerChecklistStore,
} from "./server-checklist"

export const SERVER_POLICY_ITEMS = [
  "초기 질문 답변, 위험 질문 답변, 절차별 '안내 확인' 상태를 로그인한 계정(서버)에 저장합니다.",
  "이 기기 저장과는 따로 동의를 받습니다. AI 대화는 서버에 저장하지 않습니다.",
  "서버 기록과 이 기기 기록은 자동으로 합치지 않습니다.",
  "서버 저장 동의를 철회하면 서버의 체크리스트 기록을 삭제합니다.",
]

const SAVE_STATUS_LABELS = {
  idle: "",
  saving: "서버에 저장하는 중…",
  saved: "● 계정(서버)에 저장 중",
  failed: "⚠ 서버에 저장하지 못했습니다. 화면과 이 기기 기록은 그대로입니다.",
} as const

export function ServerSaveBand() {
  const accountId = useAuthStore((s) => s.accountId)
  const { consent, saveStatus, pending, declined, revokeResult } = useServerChecklistStore()
  const storeAccount = useServerChecklistStore((s) => s.accountId)
  // 서버로 보낼 답이 있는지. 없으면 [서버에 저장]·[이 기기 내용으로 서버 덮어쓰기]를 보여 주지 않는다.
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  const [checked, setChecked] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  // 서버 저장 동의 모달 열림
  const [consentOpen, setConsentOpen] = useState(false)
  // 사용자가 닫은 서버 기록. 새 서버 기록(다른 로그인 등)이 오면 다시 한 번 저절로 연다.
  const [dismissedPending, setDismissedPending] = useState<ChecklistSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const checkboxId = useId()

  // 비로그인이거나 아직 이 계정의 상태가 아니면 보이지 않는다(다른 계정 상태 노출 방지).
  if (!accountId || storeAccount !== accountId) return null

  const run = async (task: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await task()
    } finally {
      setBusy(false)
    }
  }

  const revokeNotice = revokeResult && (
    <Notice tone={revokeResult.ok ? "success" : "danger"} className="space-y-2">
      {revokeResult.ok ? (
        <p>서버 저장 동의를 철회하고 서버의 체크리스트 기록을 삭제했습니다.</p>
      ) : (
        <>
          <p>
            서버 기록을 삭제하지 못했습니다. 서버에 체크리스트 기록이 남아 있고 서버 저장 동의도
            그대로입니다. 이 기기 기록에는 영향이 없습니다.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void run(() => revokeServerSave(accountId))}
          >
            서버 삭제 다시 시도
          </Button>
        </>
      )}
    </Notice>
  )

  if (consent === "off" || consent === "checking") {
    return (
      <p role="status" className="text-xs text-muted-foreground">
        서버 저장 상태 확인 중…
      </p>
    )
  }

  if (consent === "unknown") {
    return (
      <Notice tone="warning" className="space-y-2">
        <p>서버 저장 상태를 확인하지 못했습니다.</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void run(() => recheckServerSave(accountId))}
        >
          다시 확인
        </Button>
      </Notice>
    )
  }

  if (consent === "none") {
    // 답이 없으면 동의를 묻지 않는다(보낼 내용이 없다). 직전 철회 결과만 남긴다.
    if (!hasAnswers) return revokeNotice
    if (declined) {
      return (
        <div className="space-y-2">
          <p
            role="status"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-dashed px-3 py-1 text-sm font-medium text-muted-foreground"
          >
            서버 저장 · 저장 안 함
          </p>
          {revokeNotice}
        </div>
      )
    }
    return (
      <section aria-label="서버 저장" className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {/* 최신 시안: 서버 저장 상태 칸 + [서버 저장] */}
          <p className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-dashed px-3 py-1 text-sm font-medium text-muted-foreground">
            서버 저장 · 미동의
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            aria-haspopup="dialog"
            onClick={() => setConsentOpen(true)}
          >
            <Settings2 className="size-3.5" aria-hidden />
            서버 저장
          </Button>
        </div>
        {revokeNotice}
        {consentOpen && (
          <Modal onClose={() => setConsentOpen(false)}>
            <Modal.Header title={`로그인한 계정(서버)에도 체크리스트를 저장할까요?`} />
            <Modal.Body>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                {SERVER_POLICY_ITEMS.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <div className="flex items-center gap-2">
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => setChecked(event.target.checked)}
                />
                <label htmlFor={checkboxId}>서버 저장 정책을 확인했습니다</label>
              </div>
              {saveStatus === "failed" && (
                <p role="alert" className="text-danger-foreground">
                  서버에 저장하지 못했습니다. 동의는 기록되지 않았습니다. 다시 시도해 주세요.
                </p>
              )}
            </Modal.Body>
            <Modal.Actions>
              <Button type="button" variant="outline" onClick={declineServerSave}>
                저장 안 함
              </Button>
              <Button
                type="button"
                disabled={!checked || busy}
                onClick={() => void run(() => grantServerSave(accountId))}
              >
                서버에 저장
              </Button>
            </Modal.Actions>
          </Modal>
        )}
      </section>
    )
  }

  // consent === "granted"
  // 서버 기록이 있고 사용자가 아직 닫지 않았으면 고르는 모달을 연다.
  const choiceOpen = pending !== null && pending !== dismissedPending
  return (
    <section aria-label="서버 저장" className="flex flex-wrap items-center gap-2">
      {pending ? (
        <>
          <p
            role="status"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-dashed px-3 py-1 text-sm font-medium text-muted-foreground"
          >
            서버 저장 멈춤 · 서버 기록 선택 필요
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setDismissedPending(null)}
          >
            선택하기
          </Button>
        </>
      ) : (
        <p
          role="status"
          className={
            SAVE_STATUS_LABELS[saveStatus]
              ? "inline-flex min-h-9 items-center gap-1.5 rounded-md border border-dashed px-3 py-1 text-sm font-medium text-muted-foreground"
              : "inline-flex min-h-9 items-center gap-1.5 rounded-md border border-success-foreground/30 bg-success px-3 py-1 text-sm font-medium text-success-foreground"
          }
        >
          {SAVE_STATUS_LABELS[saveStatus] || "● 계정(서버)에 저장 중"}
        </p>
      )}
      {choiceOpen && (
        <Modal onClose={() => setDismissedPending(pending)}>
          <Modal.Header
            title="계정(서버)에 저장된 체크리스트가 있습니다"
            subtitle={
              hasAnswers
                ? "자동으로 합치지 않으니 사용할 기록을 골라 주세요."
                : "불러오면 화면에 표시합니다."
            }
          />
          <Modal.Actions>
            <Button type="button" onClick={() => loadServerRecord(accountId)}>
              서버 기록 불러오기
            </Button>
            {hasAnswers && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void run(() => keepLocalOverServer(accountId))}
              >
                이 기기 내용으로 서버 덮어쓰기
              </Button>
            )}
          </Modal.Actions>
        </Modal>
      )}
      {saveStatus === "failed" && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void run(() => retryServerSave(accountId))}
        >
          서버 저장 다시 시도
        </Button>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => setConfirmRevoke(true)}
      >
        서버 저장 철회
      </Button>
      {/* 한 줄(flex) 안에서도 안내가 폭 전체를 쓰게 한다 */}
      {revokeNotice && <div className="w-full">{revokeNotice}</div>}
      {confirmRevoke && (
        <ConfirmDialog
          title="서버 저장 동의를 철회할까요?"
          actions={[
            {
              label: "철회하고 서버 기록 삭제",
              primary: true,
              danger: true,
              onClick: () => {
                setConfirmRevoke(false)
                void run(() => revokeServerSave(accountId))
              },
            },
          ]}
          onCancel={() => setConfirmRevoke(false)}
        >
          <p className="text-sm text-muted-foreground">
            계정(서버)의 체크리스트 기록을 지우고 서버 저장 동의를 해제합니다. 이 기기 기록과 화면은
            그대로입니다.
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}
