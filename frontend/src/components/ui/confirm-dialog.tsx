/*
 * 담당: [A] | 책임: 확인창(새 대화 S8·이탈 S11·삭제·철회 확인 공용).
 * 구현: 화면정의서 17장 접근성 — 열리면 첫 버튼에 포커스, Esc는 취소, 제목을 대화상자 이름으로 읽게 한다.
 */
import { type ReactNode, useEffect, useId, useRef } from "react"
import { Button } from "@/components/ui/button"

export type ConfirmAction = {
  label: string
  onClick: () => void
  primary?: boolean
  // 되돌릴 수 없는 동작(삭제·철회)은 빨간 버튼으로 보인다.
  danger?: boolean
}

// #227 시안 확인창 모양: 공통 모달과 같은 틀(테두리·어두운 배경), 제목 18px, 버튼은 오른쪽에 가로로
//   [취소] → 보조 동작 → 주된 동작 순서(주된 동작이 맨 오른쪽). 처음 초점은 주된 동작에 둔다(전과 같음).
export function ConfirmDialog({
  title,
  children,
  actions,
  onCancel,
}: {
  title: string
  children?: ReactNode
  actions: ConfirmAction[]
  onCancel: () => void
}) {
  const titleId = useId()
  const primaryButton = useRef<HTMLButtonElement>(null)
  const ordered = [...actions.filter((a) => !a.primary), ...actions.filter((a) => a.primary)]
  const focusTarget = actions.find((a) => a.primary) ?? actions[0]

  useEffect(() => {
    primaryButton.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 sm:p-8">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        // 공통 모달과 같은 황금비 규칙(좁음 400px, 여백 20/32px, 사이 20px, 모서리 14px).
        className="max-h-[calc(100dvh-2rem)] w-full max-w-[25rem] space-y-group overflow-y-auto rounded-xl border bg-card p-group text-card-foreground shadow-lg sm:p-block"
      >
        <h2 id={titleId} className="text-lg font-semibold leading-snug">
          {title}
        </h2>
        {children}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            취소
          </Button>
          {ordered.map((action) => (
            <Button
              key={action.label}
              ref={action === focusTarget ? primaryButton : undefined}
              type="button"
              variant={action.danger ? "destructive" : action.primary ? "default" : "outline"}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  )
}
