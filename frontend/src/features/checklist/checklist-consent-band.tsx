/*
 * 담당: [A] | 책임: W-02 체크리스트 저장 상태 한 줄과 [저장 설정] 모달(COMMON-01·02 중 체크리스트 ①).
 * PRD: 태스크 4-1-1(W-02), 4-1-2, 4-1-3, 4-2-4. 화면정의서 D-03·D-10·D-14, 17장 접근성. 정책 P01-C.
 * 구현: 화면에는 저장 상태와 [저장 설정] 버튼만 두고, 누르면 모달에서 저장 정책·확인 체크·[저장]·[저장 안 함]을 보인다
 *   (#197, 현주 님 UI 제안·디자인 시스템 7.4 "저장 설정은 모달"). 화면을 가볍게 하고 선택을 한곳에 모으기 위해서다.
 *   확인 체크를 해야 [저장]이 눌린다. [저장]·[저장 안 함]은 기본 선택 없이 동등하다.
 *   저장·저장 안 함을 고르면 상태가 바뀌어 모달이 저절로 닫힌다. Esc·바깥 누르기로 닫으면 아무것도 고르지 않은 것이다.
 *   상태는 문구와 기호를 함께 써서 색만으로 구분하지 않는다.
 *   #227 최신 시안(사용자 지시 2026-10-29): 화면에는 저장 상태 칸 하나와 [저장]만 둔다. 저장 중이면 [저장]이 정책과
 *   [저장 동의 철회]를 보이는 모달을 연다(철회 확인·결과 안내는 체크리스트 화면이 onRevoke로 처리). [저장 안 함]을 고른 뒤에도
 *   [저장]으로 다시 고를 수 있다. 상태 칸은 기호(○ ✓ ⚠)와 글자를 함께 바꿔 색만으로 구분하지 않는다.
 *   추가 개선 지시서 3장: 저장 모달의 열림 상태를 공용 스토어(useChecklistSaveModal)로 옮겨, 띠의 [저장]과 플로팅
 *   내비게이션 [저장]이 같은 모달을 연다. 모달은 한 곳에서만 그린다 — 띠가 화면에 있으면 띠 안에서, 없으면(다른 화면)
 *   플로팅 내비게이션의 호스트(storage-settings.tsx)가 그린다. 미동의면 모달 위쪽에 "미동의 · 저장 안 됨 · 새로고침하면
 *   사라집니다"를 주의 색으로 보인다(저장 중이면 보이지 않는다).
 * 제한사항: AI 대화 동의(W-07)는 별도다. 정책 문구는 P02 검토 전 초안이며 #197에서 문구는 바꾸지 않았다.
 */
import { Check, Circle, Settings2, TriangleAlert } from "lucide-react"
import { useEffect, useId, useState } from "react"
import { create } from "zustand"
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"
import { cn } from "@/lib/utils"
import { CONSENT_COPY, STORAGE_STATUS_LABELS } from "@/shared/content/checklist"
import { inheritanceDb } from "@/shared/storage/db"
import {
  declineChecklistStorage,
  grantChecklistStorage,
  useChecklistStorageStore,
} from "./checklist-storage"

export const POLICY_ITEMS = [
  "초기 질문 답변, 위험 질문 답변, 절차별 '안내 확인' 상태를 이 기기(브라우저)에만 저장합니다. 서버로 보내지 않습니다.",
  "이 기기를 함께 쓰는 사람도 저장된 내용을 볼 수 있습니다. 공용 기기에서는 저장하지 마세요.",
  "AI 대화 저장과는 따로 동의를 받습니다.",
  "저장한 내용은 언제든 지우거나 동의를 철회할 수 있습니다.",
]

// 저장 모달 열림 상태(공용). hosts: 지금 모달을 그릴 수 있는 띠의 수(0이면 플로팅 호스트가 그린다).
type SaveModalState = {
  open: boolean
  hosts: number
  setOpen: (open: boolean) => void
  addHost: () => void
  removeHost: () => void
}
export const useChecklistSaveModal = create<SaveModalState>((set) => ({
  open: false,
  hosts: 0,
  setOpen: (open) => set({ open }),
  addHost: () => set((s) => ({ hosts: s.hosts + 1 })),
  removeHost: () => set((s) => ({ hosts: Math.max(s.hosts - 1, 0) })),
}))

// 저장 상태 칸(시안): 저장 중 = 초록 ✓ "기기 저장", 미동의 = 점선 ○ 긴 안내, 저장 불가 = 빨간 글자
export function ChecklistStatusChip() {
  const status = useChecklistStorageStore((s) => s.status)
  if (status === "checking")
    return (
      <span role="status" className="text-sm text-muted-foreground">
        저장 상태 확인 중…
      </span>
    )
  if (status === "failed")
    return (
      <span role="status" className="text-sm text-danger-foreground">
        {STORAGE_STATUS_LABELS.failed}
      </span>
    )
  const on = status === "ready"
  return (
    <span
      role="status"
      className={cn(
        "inline-flex min-h-9 items-center gap-1.5 rounded-md border px-3 py-1 text-sm font-medium",
        on
          ? "border-success-foreground/30 bg-success text-success-foreground"
          : "border-dashed text-muted-foreground",
      )}
    >
      {on ? (
        <Check className="size-3.5 shrink-0" aria-hidden />
      ) : (
        <Circle className="size-3.5 shrink-0" aria-hidden />
      )}
      <span className="sr-only">체크리스트 </span>
      {on ? "기기 저장" : STORAGE_STATUS_LABELS["not-consented"]}
    </span>
  )
}

// 저장 모달(기존 모달 그대로). 띠와 플로팅 호스트가 함께 쓴다.
export function ChecklistSaveModal({ onRevoke }: { onRevoke?: () => void }) {
  const status = useChecklistStorageStore((s) => s.status)
  const open = useChecklistSaveModal((s) => s.open)
  const setOpen = useChecklistSaveModal((s) => s.setOpen)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const checkboxId = useId()
  const close = () => setOpen(false)

  const onSave = async () => {
    setSaving(true)
    await grantChecklistStorage(inheritanceDb)
    setSaving(false)
    setOpen(false)
  }
  const onDecline = () => {
    declineChecklistStorage()
    setOpen(false)
  }

  if (!open) return null
  if (status === "ready")
    return (
      <Modal onClose={close}>
        <Modal.Header title="체크리스트 저장" />
        <Modal.Body>
          <ChecklistStatusChip />
          <ul className="list-disc space-y-1.5 pl-5 text-base text-muted-foreground">
            {POLICY_ITEMS.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Modal.Body>
        <Modal.Actions>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOpen(false)
              onRevoke?.()
            }}
          >
            저장 동의 철회
          </Button>
          <Button type="button" onClick={close}>
            닫기
          </Button>
        </Modal.Actions>
      </Modal>
    )
  if (status === "not-consented")
    return (
      <Modal onClose={close}>
        <Modal.Header title={CONSENT_COPY.checklist.question} />
        <Modal.Body>
          {/* 미동의 상태: 동의 여부·저장 여부와 유실 위험을 나눠 주의 색으로 보인다. */}
          <div
            role="note"
            aria-label="지금 저장 상태"
            className="space-y-1 rounded-md border border-warning-foreground/30 bg-warning px-3 py-2.5 text-warning-foreground"
          >
            <p className="flex items-center gap-1.5 text-sm font-semibold">
              <TriangleAlert className="size-4 shrink-0" aria-hidden />
              미동의 · 저장 안 됨
            </p>
            <p className="text-sm">새로고침하면 사라집니다.</p>
          </div>
          <ul className="list-disc space-y-1.5 pl-5 text-base text-muted-foreground">
            {POLICY_ITEMS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <label htmlFor={checkboxId} className="flex min-h-11 items-center gap-3 text-base">
            <input
              id={checkboxId}
              type="checkbox"
              className="size-5 accent-primary"
              checked={checked}
              onChange={(event) => setChecked(event.target.checked)}
            />
            저장 정책을 확인했습니다
          </label>
        </Modal.Body>
        <Modal.Actions>
          <Button type="button" variant="outline" onClick={onDecline}>
            저장 안 함
          </Button>
          <Button type="button" disabled={!checked || saving} onClick={onSave}>
            저장
          </Button>
        </Modal.Actions>
      </Modal>
    )
  // 확인 중·저장 불가: 고를 것이 없어 지금 상태만 보인다(플로팅 [저장]을 눌렀을 때 반응이 없지 않게).
  return (
    <Modal onClose={close}>
      <Modal.Header title="체크리스트 저장" />
      <Modal.Body>
        <ChecklistStatusChip />
      </Modal.Body>
      <Modal.Actions>
        <Button type="button" onClick={close}>
          닫기
        </Button>
      </Modal.Actions>
    </Modal>
  )
}

export function ChecklistConsentBand({ onRevoke }: { onRevoke?: () => void }) {
  const status = useChecklistStorageStore((s) => s.status)
  const setOpen = useChecklistSaveModal((s) => s.setOpen)
  const addHost = useChecklistSaveModal((s) => s.addHost)
  const removeHost = useChecklistSaveModal((s) => s.removeHost)
  // 이 띠가 화면에 있는 동안은 모달을 띠 안에서 그린다(철회 확인·결과 안내가 이 화면에 이어지게).
  useEffect(() => {
    addHost()
    return removeHost
  }, [addHost, removeHost])

  const canOpen = status === "ready" || status === "not-consented"
  return (
    <section aria-label="체크리스트 저장" className="flex flex-wrap items-center gap-2">
      <ChecklistStatusChip />
      {canOpen && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-haspopup="dialog"
          onClick={() => setOpen(true)}
        >
          <Settings2 className="size-3.5" aria-hidden />
          저장
        </Button>
      )}
      <ChecklistSaveModal onRevoke={onRevoke} />
    </section>
  )
}
