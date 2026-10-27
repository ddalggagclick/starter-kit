/*
 * 담당: [A] | 책임: W-07 AI 대화 저장 동의 띠(S1), 이전 대화 목록(S10).
 * PRD: 태스크 4-1-1(W-07), 3-6-2, 3-6-3. 화면정의서 D-03·D-05·D-10·D-14, 17장 접근성.
 * 구현: 동의는 정책 확인 체크 후 [저장]만 가능하고 [저장]·[저장 안 함]은 기본 선택 없이 동등하다.
 *   #197(현주 님 UI 제안·디자인 시스템 7.4, 체크리스트와 같은 방식): 화면에는 상태 한 줄과 [저장 설정]만 두고,
 *   누르면 모달에서 정책·확인 체크·[저장]·[저장 안 함]을 보인다. 고르면 상태가 바뀌어 모달이 저절로 닫힌다.
 *   상태는 문구·기호로 표시해 색만으로 구분하지 않는다.
 * 제한사항: 정책 문구는 P02 검토 전 초안이다. [대화 기록 삭제] 전체 삭제·동의 철회(4-3)는 후속 이슈다.
 */
import { useId, useState } from "react"
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"
import { CONSENT_COPY, STORAGE_STATUS_LABELS } from "@/shared/content/checklist"
import type { ConversationRecord } from "@/shared/storage/db"
import { type ChatStorageStatus, conversationDate } from "./chat-storage"

export const CHAT_POLICY_ITEMS = [
  "질문과 AI 답변·공식 출처를 이 기기(브라우저)에만 저장합니다. 서버로 보내지 않습니다.",
  "이 기기를 함께 쓰는 사람도 저장된 대화를 볼 수 있습니다. 공용 기기에서는 저장하지 마세요.",
  "체크리스트 저장과는 따로 동의를 받습니다.",
  "저장한 대화는 이전 대화 목록에서 하나씩 지울 수 있습니다.",
]

export function ChatConsentBand({
  status,
  declined,
  onGrant,
  onDecline,
}: {
  status: ChatStorageStatus
  declined: boolean
  onGrant: () => Promise<boolean>
  onDecline: () => void
}) {
  const [open, setOpen] = useState(false)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const checkboxId = useId()

  if (status === "checking") {
    return (
      <p role="status" className="text-xs text-muted-foreground">
        AI 대화 저장 상태 확인 중…
      </p>
    )
  }
  if (status !== "not-consented" || declined) {
    return (
      <p role="status" className="text-xs text-muted-foreground">
        AI 대화 저장: {STORAGE_STATUS_LABELS[status]}
      </p>
    )
  }

  return (
    <section aria-label="AI 대화 저장" className="flex flex-wrap items-center gap-2">
      <p className="text-xs text-muted-foreground">
        AI 대화 저장: {STORAGE_STATUS_LABELS["not-consented"]}
      </p>
      <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
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
            <Button type="button" variant="outline" onClick={onDecline}>
              저장 안 함
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
