/*
 * 담당: [A] | 책임: 플로팅 내비게이션 [저장]이 여는 "저장 설정" 창 — 저장 기능을 모두 이 창 하나에서 끝낸다.
 * 근거: 사용자 지시(2026-10-30) "저장은 플로팅 저장에만 / 서버 저장도 따로 모달 없이 하나에서 / 각 저장 정책을 일관성 있게 /
 *   같은 위계의 동일한 요소처럼 / 저장 사이 구분선 2개".
 * 구현: 칸 세 개(이 기기 · 계정(서버) · AI 대화)를 같은 부품(components/ui/storage-section.tsx)으로 그린다.
 *   제목 + 상태 표시 → 설명 → 정책 전체 → 동작. 동의 전: 정책 확인 체크 + [저장 안 함]·[저장]. 동의 후: [저장 동의 철회].
 *   칸 사이는 두 줄 구분선. 기록을 지우는 철회만 셋 다 같은 확인창으로 한 번 더 묻는다(되돌릴 수 없는 동작, 기존 규칙).
 *   - 이 기기: 미동의면 "저장 안 됨 · 새로고침하면 사라집니다."(주의 색). [체크리스트 삭제]는 체크리스트 목록 아래에 있다.
 *   - 계정(서버): 동의·서버 기록 고르기(불러오기·덮어쓰기, 자동으로 합치지 않음)·실패 재시도·철회를 창 안에서 한다.
 *     기존 ServerSaveBand의 동작(server-checklist.ts)을 그대로 쓰고, 겹치는 모달만 없앴다. 지금 로그인 계정에 고정한다.
 *   - AI 대화: 화면에 대화창이 있을 때만(대화창의 실제 저장 동작을 연결 통로로 받는다).
 * 제한사항: 저장 계약·충돌 처리·정책 문구는 바꾸지 않았다. 정책 문구는 P02 검토 전 초안.
 */
import { Fragment, type ReactNode, useState } from "react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Modal } from "@/components/ui/modal"
import { Notice } from "@/components/ui/notice"
import {
  StorageActions,
  StorageChip,
  StorageConsentForm,
  StorageSection,
  StorageSeparator,
} from "@/components/ui/storage-section"
import { useAuthStore } from "@/features/auth/auth-store"
import { ChatStorageSettings } from "@/features/chat/chat-history"
import { useChatStorageBridge } from "@/features/chat/chat-storage-bridge"
import { STORAGE_STATUS_LABELS } from "@/shared/content/checklist"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { inheritanceDb } from "@/shared/storage/db"
import { POLICY_ITEMS, useChecklistSaveModal } from "./checklist-consent-band"
import {
  declineChecklistStorage,
  grantChecklistStorage,
  useChecklistStorageStore,
} from "./checklist-storage"
import { useChecklistStorageActions } from "./checklist-storage-controls"
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
import { SERVER_POLICY_ITEMS } from "./server-save-band"

export function ChecklistSaveModalHost() {
  const open = useChecklistSaveModal((s) => s.open)
  if (!open) return null
  return <StorageSettingsModal />
}

function StorageSettingsModal() {
  const setOpen = useChecklistSaveModal((s) => s.setOpen)
  const hasChat = useChatStorageBridge((s) => s.current !== null)
  const close = () => setOpen(false)
  const sections: ReactNode[] = [<DeviceSection key="device" />, <ServerSection key="server" />]
  if (hasChat) sections.push(<ChatStorageSettings key="chat" />)
  return (
    <Modal onClose={close}>
      <Modal.Header title="저장 설정" subtitle="항목마다 저장 여부를 따로 고를 수 있어요." />
      <Modal.Body className="space-y-0 text-base">
        {sections.map((section, index) => (
          <Fragment key={(section as { key: string }).key}>
            {index > 0 && <StorageSeparator />}
            {section}
          </Fragment>
        ))}
      </Modal.Body>
      <Modal.Actions>
        <Button type="button" onClick={close}>
          닫기
        </Button>
      </Modal.Actions>
    </Modal>
  )
}

// ① 이 기기에 저장(체크리스트)
function DeviceSection() {
  const status = useChecklistStorageStore((s) => s.status)
  const declined = useChecklistStorageStore((s) => s.declined)
  const storage = useChecklistStorageActions()
  const subject = "이 기기"
  const chip =
    status === "ready" ? (
      <StorageChip tone="on" subject={subject}>
        저장 중
      </StorageChip>
    ) : status === "not-consented" ? (
      <StorageChip tone="off" subject={subject}>
        {declined ? "저장 안 함" : "미동의"}
      </StorageChip>
    ) : status === "failed" ? (
      <StorageChip tone="warn" subject={subject}>
        저장 불가
      </StorageChip>
    ) : (
      <StorageChip tone="muted" subject={subject}>
        확인 중…
      </StorageChip>
    )
  return (
    <StorageSection
      label="이 기기 저장"
      title="이 기기에 저장"
      chip={chip}
      description="체크리스트 답변과 읽음 상태를 이 브라우저에 저장해요."
      policy={POLICY_ITEMS}
    >
      {status === "not-consented" && (
        <>
          {/* 저장 안 됨: 데이터 유실 위험을 주의 색으로 알린다(동의 여부는 위 상태 표시). */}
          <p
            role="note"
            className="rounded-md border border-warning-foreground/30 bg-warning px-3 py-2 text-sm font-medium text-warning-foreground"
          >
            저장 안 됨 · 새로고침하면 사라집니다.
          </p>
          <StorageConsentForm
            checkboxLabel="이 기기 저장 정책을 확인했습니다"
            onDecline={declineChecklistStorage}
            onSave={() => grantChecklistStorage(inheritanceDb)}
          />
        </>
      )}
      {status === "failed" && (
        <p className="text-sm text-danger-foreground">{STORAGE_STATUS_LABELS.failed}</p>
      )}
      {status === "ready" && (
        <StorageActions>
          <Button
            type="button"
            variant="outline"
            disabled={storage.busy}
            onClick={() => storage.request("revoke")}
          >
            저장 동의 철회
          </Button>
        </StorageActions>
      )}
      {storage.view}
    </StorageSection>
  )
}

// ② 계정(서버)에 저장 — 기존 ServerSaveBand 동작을 창 안에 펼친다(겹치는 모달 없음).
function ServerSection() {
  const accountId = useAuthStore((s) => s.accountId)
  const { consent, saveStatus, pending, declined, revokeResult } = useServerChecklistStore()
  const storeAccount = useServerChecklistStore((s) => s.accountId)
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  const [busy, setBusy] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  const subject = "계정(서버)"
  const ready = accountId !== null && storeAccount === accountId

  const run = async (task: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await task()
    } finally {
      setBusy(false)
    }
  }

  let chip: ReactNode
  if (!accountId)
    chip = (
      <StorageChip tone="muted" subject={subject}>
        로그인 필요
      </StorageChip>
    )
  else if (!ready || consent === "off" || consent === "checking")
    chip = (
      <StorageChip tone="muted" subject={subject}>
        확인 중…
      </StorageChip>
    )
  else if (consent === "unknown")
    chip = (
      <StorageChip tone="warn" subject={subject}>
        확인 실패
      </StorageChip>
    )
  else if (consent === "none")
    chip = (
      <StorageChip tone="off" subject={subject}>
        {declined ? "저장 안 함" : "미동의"}
      </StorageChip>
    )
  else if (pending)
    chip = (
      <StorageChip tone="warn" subject={subject}>
        기록 선택 필요
      </StorageChip>
    )
  else if (saveStatus === "saving")
    chip = (
      <StorageChip tone="muted" subject={subject}>
        저장하는 중…
      </StorageChip>
    )
  else if (saveStatus === "failed")
    chip = (
      <StorageChip tone="warn" subject={subject}>
        저장 실패
      </StorageChip>
    )
  else
    chip = (
      <StorageChip tone="on" subject={subject}>
        저장 중
      </StorageChip>
    )

  const revokeNotice = ready && accountId && revokeResult && (
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

  return (
    <StorageSection
      label="계정(서버) 저장"
      title="계정(서버)에 저장"
      chip={chip}
      description="로그인한 계정에 체크리스트를 저장해 다른 기기에서도 불러올 수 있어요."
      policy={SERVER_POLICY_ITEMS}
    >
      {!accountId && <p className="text-sm text-muted-foreground">로그인하면 사용할 수 있어요.</p>}
      {ready && accountId && consent === "unknown" && (
        <StorageActions>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void run(() => recheckServerSave(accountId))}
          >
            다시 확인
          </Button>
        </StorageActions>
      )}
      {ready &&
        accountId &&
        consent === "none" &&
        (hasAnswers ? (
          <StorageConsentForm
            checkboxLabel="서버 저장 정책을 확인했습니다"
            onDecline={declineServerSave}
            onSave={() => run(() => grantServerSave(accountId))}
            busy={busy}
            error={
              saveStatus === "failed" && (
                <p role="alert" className="text-sm text-danger-foreground">
                  서버에 저장하지 못했습니다. 동의는 기록되지 않았습니다. 다시 시도해 주세요.
                </p>
              )
            }
          />
        ) : (
          <p className="text-sm text-muted-foreground">체크리스트에 답하면 저장할 수 있어요.</p>
        ))}
      {ready && accountId && consent === "granted" && (
        <>
          {/* 서버 기록 고르기: 자동으로 합치지 않고 사용자가 고른다(기존 규칙). 창 안에 바로 펼친다. */}
          {pending && (
            <div className="space-y-item rounded-md border border-warning-foreground/30 bg-warning px-3 py-3">
              <p className="text-sm font-semibold text-warning-foreground">
                계정(서버)에 저장된 체크리스트가 있습니다
              </p>
              <p className="text-sm text-warning-foreground">
                {hasAnswers
                  ? "자동으로 합치지 않으니 사용할 기록을 골라 주세요. 고르기 전에는 서버 저장을 멈춥니다."
                  : "불러오면 화면에 표시합니다."}
              </p>
              <StorageActions>
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
                <Button type="button" onClick={() => loadServerRecord(accountId)}>
                  서버 기록 불러오기
                </Button>
              </StorageActions>
            </div>
          )}
          {saveStatus === "failed" && (
            <p className="text-sm text-danger-foreground">
              서버에 저장하지 못했습니다. 화면과 이 기기 기록은 그대로입니다.
            </p>
          )}
          <StorageActions>
            {saveStatus === "failed" && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void run(() => retryServerSave(accountId))}
              >
                서버 저장 다시 시도
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setConfirmRevoke(true)}
            >
              저장 동의 철회
            </Button>
          </StorageActions>
        </>
      )}
      {revokeNotice}
      {confirmRevoke && accountId && (
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
    </StorageSection>
  )
}
