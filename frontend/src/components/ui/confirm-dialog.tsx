/*
 * 담당: [A] | 책임: 확인창(새 대화 S8·이탈 S11·삭제·철회 확인 공용).
 * 구현: 화면정의서 17장 접근성 — 열리면 첫 버튼에 포커스, Esc는 취소, 제목을 대화상자 이름으로 읽게 한다.
 */
import { type ReactNode, useEffect, useId, useRef } from "react"
import { Button } from "@/components/ui/button"

export type ConfirmAction = { label: string; onClick: () => void; primary?: boolean }

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
  const firstButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    firstButton.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-sm space-y-3 rounded-xl border bg-card p-4 shadow-lg"
      >
        <p id={titleId} className="font-semibold">
          {title}
        </p>
        {children}
        <div className="flex flex-col gap-2">
          {actions.map((action, index) => (
            <Button
              key={action.label}
              ref={index === 0 ? firstButton : undefined}
              type="button"
              variant={action.primary ? "default" : "outline"}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
          <Button type="button" variant="outline" onClick={onCancel}>
            취소
          </Button>
        </div>
      </div>
    </div>
  )
}
