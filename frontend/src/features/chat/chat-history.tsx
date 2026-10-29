/*
 * 담당: [A] | 책임: W-07 AI 대화 저장 동의 띠(S1), 이전 대화 목록(S10).
 * PRD: 태스크 4-1-1(W-07), 3-6-2, 3-6-3. 화면정의서 D-03·D-05·D-10·D-14, 17장 접근성.
 * 구현: 동의는 정책 확인 체크 후 [저장]만 가능하고 [저장]·[저장 안 함]은 기본 선택 없이 동등하다.
 *   #197(현주 님 UI 제안·디자인 시스템 7.4, 체크리스트와 같은 방식): 화면에는 상태 한 줄과 [저장 설정]만 두고,
 *   누르면 모달에서 정책·확인 체크·[저장]·[저장 안 함]을 보인다. 고르면 상태가 바뀌어 모달이 저절로 닫힌다.
 *   상태는 문구·기호로 표시해 색만으로 구분하지 않는다.
 *   #227(새 시안, 모양만 변경): 상태 한 줄을 작은 표시로 바꿨다. 저장 안 됨은 회색 점선 ○, 저장 중은 초록 ✓.
 *   [저장 설정]·모달·동의 흐름은 그대로다.
 *   #227 사용자 요청: 저장 중이면 [저장 설정]을 숨기고, "✓ 저장 중" 표시를 버튼으로 둔다. 누르면 저장 설정 모달
 *   (상태·정책·[저장 동의 철회]·[닫기])이 열린다. 철회 확인창·결과 안내는 쓰는 쪽(onRevoke)이 처리한다.
 * 제한사항: 정책 문구는 P02 검토 전 초안이다. [대화 기록 삭제] 전체 삭제·동의 철회(4-3)는 후속 이슈다.
 */
import { Check, Circle, type LucideIcon, Settings2, TriangleAlert } from "lucide-react"
import { useId, useState } from "react"
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"
import { cn } from "@/lib/utils"
import { CHAT_SAVE_BADGE_LABELS } from "@/shared/content/chat"
import { CONSENT_COPY } from "@/shared/content/checklist"
import type { ConversationRecord } from "@/shared/storage/db"
import { type ChatStorageStatus, conversationDate } from "./chat-storage"

// #227 새 시안: 대화창 위쪽 줄의 버튼과 저장 상태 표시를 모두 같은 크기(높이 32px, 글자 12px, 아이콘 14px)로 맞춘다.
//   첫 화면 대화창의 [이전 대화]·[새 대화]도 이 모양을 쓴다.
// 최신 시안(NgrnTfYvGvuGj5PYWnJcfu): 높이 36px, 글자 14px로 키웠다.
export const CHAT_TOOL_BUTTON_CLASS = "gap-1.5"

const SAVE_BADGE_TONES: Record<ChatStorageStatus, string> = {
  checking: "border-dashed text-muted-foreground",
  "not-consented": "border-dashed text-muted-foreground",
  ready: "border-success-foreground/30 bg-success text-success-foreground",
  failed: "border-warning-foreground/20 bg-warning text-warning-foreground",
}

const SAVE_BADGE_ICONS: Record<ChatStorageStatus, LucideIcon> = {
  checking: Circle,
  "not-consented": Circle,
  ready: Check,
  failed: TriangleAlert,
}

// 저장 상태 표시. 색과 함께 기호(○ ✓ ⚠)와 글자도 바뀌어 색만으로 구분하지 않는다.
// 보이는 글자는 짧게 두고, 화면낭독기에는 "AI 대화 저장 안 됨"처럼 무엇의 상태인지 함께 읽힌다.
function SaveStatusBadge({ status }: { status: ChatStorageStatus }) {
  const Icon = SAVE_BADGE_ICONS[status]
  return (
    <span
      role="status"
      className={cn(
        "inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium",
        SAVE_BADGE_TONES[status],
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">AI 대화 </span>
      {CHAT_SAVE_BADGE_LABELS[status]}
    </span>
  )
}

export const CHAT_POLICY_ITEMS = [
  "질문과 AI 답변·공식 출처를 이 기기(브라우저)에만 저장합니다. 서버로 보내지 않습니다.",
  "이 기기를 함께 쓰는 사람도 저장된 대화를 볼 수 있습니다. 공용 기기에서는 저장하지 마세요.",
  "체크리스트 저장과는 따로 동의를 받습니다.",
  "저장한 대화는 이전 대화 목록에서 하나씩 지울 수 있습니다.",
]

// 저장 중일 때의 상태 표시 겸 버튼. 누르면 저장 설정 모달을 연다(철회는 onRevoke로 넘긴다).
function SavingStatusButton({ onRevoke }: { onRevoke?: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        // 보이는 글자("저장 중")를 이름에 담고, 누르면 저장 설정이 열림을 함께 알린다.
        aria-label="AI 대화 저장 중, 저장 설정 열기"
        title="저장 설정"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium outline-none transition-colors hover:brightness-95 focus-visible:ring-[3px] focus-visible:ring-ring/50 max-md:min-h-11",
          SAVE_BADGE_TONES.ready,
        )}
      >
        <Check className="size-3.5" aria-hidden />
        <span role="status">
          <span className="sr-only">AI 대화 </span>
          {CHAT_SAVE_BADGE_LABELS.ready}
        </span>
      </button>
      {open && (
        <Modal onClose={() => setOpen(false)}>
          <Modal.Header title="AI 대화 저장" />
          <Modal.Body>
            <SaveStatusBadge status="ready" />
            <ul className="list-disc space-y-1.5 pl-5 text-base text-muted-foreground">
              {CHAT_POLICY_ITEMS.slice(0, 2).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Modal.Body>
          <Modal.Actions>
            {onRevoke && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setOpen(false)
                  onRevoke()
                }}
              >
                저장 동의 철회
              </Button>
            )}
            <Button type="button" onClick={() => setOpen(false)}>
              닫기
            </Button>
          </Modal.Actions>
        </Modal>
      )}
    </>
  )
}

export function ChatConsentBand({
  status,
  declined,
  onGrant,
  onDecline,
  onRevoke,
}: {
  status: ChatStorageStatus
  declined: boolean
  onGrant: () => Promise<boolean>
  onDecline: () => void
  // 저장 중 모달의 [저장 동의 철회]를 눌렀을 때(없으면 버튼을 숨긴다)
  onRevoke?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const checkboxId = useId()

  // 저장 중: [저장 설정] 없이 "✓ 저장 중" 버튼만(누르면 저장 설정).
  if (status === "ready") return <SavingStatusButton onRevoke={onRevoke} />
  // 확인 중·저장 불가·[저장 안 함]을 고른 뒤에는 상태만 보인다(전과 같은 조건).
  if (status !== "not-consented" || declined) {
    return <SaveStatusBadge status={status} />
  }

  return (
    <section aria-label="AI 대화 저장" className="flex flex-wrap items-center gap-1.5">
      <SaveStatusBadge status="not-consented" />
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={CHAT_TOOL_BUTTON_CLASS}
        onClick={() => setOpen(true)}
      >
        <Settings2 className="size-3.5" aria-hidden />
        저장 설정
      </Button>
      {open && (
        <Modal onClose={() => setOpen(false)}>
          <Modal.Header title={CONSENT_COPY.chat.question} subtitle={CONSENT_COPY.chat.note} />
          <Modal.Body>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {CHAT_POLICY_ITEMS.map((item) => (
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
              <label htmlFor={checkboxId}>AI 대화 저장 정책을 확인했습니다</label>
            </div>
          </Modal.Body>
          <Modal.Actions>
            <Button type="button" variant="outline" onClick={onDecline}>
              저장 안 함
            </Button>
            <Button
              type="button"
              disabled={!checked || saving}
              onClick={async () => {
                setSaving(true)
                await onGrant()
                setSaving(false)
              }}
            >
              저장
            </Button>
          </Modal.Actions>
        </Modal>
      )}
    </section>
  )
}

export function PreviousConversations({
  conversations,
  currentId,
  onOpen,
  onRemove,
}: {
  conversations: ConversationRecord[]
  currentId: string | null
  onOpen: (conversation: ConversationRecord) => void
  onRemove: (conversation: ConversationRecord) => void
}) {
  if (conversations.length === 0) {
    return <p className="text-sm text-muted-foreground">저장된 대화가 없습니다.</p>
  }
  return (
    <ul aria-label="이전 대화" className="space-y-1">
      {conversations.map((conversation) => (
        <li
          key={conversation.id}
          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
        >
          <button
            type="button"
            className="min-w-0 flex-1 truncate text-left underline-offset-4 hover:underline"
            aria-current={conversation.id === currentId ? "true" : undefined}
            onClick={() => onOpen(conversation)}
          >
            {conversationDate(conversation.updatedAt)} · {conversation.title}
          </button>
          <button
            type="button"
            className="shrink-0 text-xs text-danger-foreground underline"
            // 무엇을 지우는지 화면낭독기가 읽게 한다(17장).
            aria-label={`삭제: ${conversation.title}`}
            onClick={() => onRemove(conversation)}
          >
            삭제
          </button>
        </li>
      ))}
    </ul>
  )
}
