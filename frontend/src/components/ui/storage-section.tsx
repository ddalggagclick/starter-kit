/*
 * 담당: [A] | 책임: 저장 설정 창의 칸(이 기기·계정(서버)·AI 대화 저장)이 함께 쓰는 같은 모양 부품.
 * 근거: 사용자 지시(2026-10-30) "저장 정책을 일관성 있게, 같은 저장이라는 위계 안에서 동일한 요소처럼, 칸 사이 구분선 2개".
 * 구현: 칸 = 제목 + 상태 표시(오른쪽) → 한 줄 설명 → 정책 전체 목록 → 동작. 상태 표시는 기호(✓ ○ ⚠)와 글자를 함께 바꿔
 *   색만으로 구분하지 않는다. 동의 전 동작은 "…저장 정책을 확인했습니다" 체크 + [저장 안 함]·[저장]으로 셋 다 같다.
 *   칸과 칸 사이는 두 줄 구분선(StorageSeparator)으로 다른 저장임을 알린다. 간격은 황금비 리듬(item 12 · group 20).
 * 제한사항: 저장 동작·정책 문구는 쓰는 쪽(각 저장 기능)이 넘긴다. 이 부품은 모양만 맡는다.
 */
import { Check, Circle, Loader, TriangleAlert } from "lucide-react"
import { type ReactNode, useId, useState } from "react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type StorageTone = "on" | "off" | "warn" | "muted"

const TONE_CLASS: Record<StorageTone, string> = {
  on: "border-success-foreground/30 bg-success text-success-foreground",
  off: "border-dashed text-muted-foreground",
  warn: "border-warning-foreground/30 bg-warning text-warning-foreground",
  muted: "border-transparent text-muted-foreground",
}
const TONE_ICON = { on: Check, off: Circle, warn: TriangleAlert, muted: Loader } as const

// 상태 표시. subject는 화면낭독기에 "이 기기 저장 중"처럼 무엇의 상태인지 함께 읽히게 한다.
export function StorageChip({
  tone,
  subject,
  children,
}: {
  tone: StorageTone
  subject: string
  children: ReactNode
}) {
  const Icon = TONE_ICON[tone]
  return (
    <span
      role="status"
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-medium",
        TONE_CLASS[tone],
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">{subject} </span>
      {children}
    </span>
  )
}

export function StorageSection({
  label,
  title,
  chip,
  description,
  policy,
  children,
}: {
  label: string
  title: string
  chip: ReactNode
  description: string
  policy: readonly string[]
  children?: ReactNode
}) {
  return (
    <section aria-label={label} className="space-y-item">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-primary">{title}</h3>
        {chip}
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {policy.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {children}
    </section>
  )
}

// 동의 전 동작(셋 다 같다): 정책 확인 체크 → [저장 안 함]·[저장]. 체크해야 [저장]이 눌린다.
export function StorageConsentForm({
  checkboxLabel,
  onDecline,
  onSave,
  busy = false,
  error,
}: {
  checkboxLabel: string
  onDecline: () => void
  onSave: () => unknown
  busy?: boolean
  error?: ReactNode
}) {
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const checkboxId = useId()
  return (
    <div className="space-y-item">
      <label htmlFor={checkboxId} className="flex min-h-11 items-center gap-3 text-base">
        <input
          id={checkboxId}
          type="checkbox"
          className="size-5 accent-primary"
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
        />
        {checkboxLabel}
      </label>
      {error}
      <StorageActions>
        <Button type="button" variant="outline" onClick={onDecline}>
          저장 안 함
        </Button>
        <Button
          type="button"
          disabled={!checked || saving || busy}
          onClick={async () => {
            setSaving(true)
            try {
              await onSave()
            } finally {
              setSaving(false)
            }
          }}
        >
          저장
        </Button>
      </StorageActions>
    </div>
  )
}

export function StorageActions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap justify-end gap-2">{children}</div>
}

// 칸 사이 두 줄 구분선: 같은 창 안이지만 서로 다른 저장임을 알린다.
export function StorageSeparator() {
  return (
    <div aria-hidden className="space-y-[3px] py-group">
      <hr className="border-border" />
      <hr className="border-border" />
    </div>
  )
}
