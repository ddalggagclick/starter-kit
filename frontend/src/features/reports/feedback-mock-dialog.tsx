/*
 * 담당: [A] | 책임: W-08 정보 오류 제보 Mock 버튼·모달.
 * PRD: E2 / 스토리 2-6 / 태스크 2-6-3, 2-6-4.
 * 구현: 버튼으로 모달을 열고 닫기·취소·Esc로 닫는다. 입력칸은 두지 않는다.
 * 완료 기준: 실제 전송·저장 요청이 없고 '준비 중'임이 보인다.
 * 제한사항: 외부 Google Forms 주소는 정해지지 않았다. 피드백 등록·메일 발송은 MVP 이후다.
 */
import { MessageSquareWarning } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { FEEDBACK_MOCK_COPY } from "@/shared/content/general-info"

export function FeedbackMockButton({ context }: { context?: string }) {
  const [open, setOpen] = useState(false)
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

  const close = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  return (
    <>
      <Button ref={triggerRef} variant="outline" size="sm" onClick={() => setOpen(true)}>
        <MessageSquareWarning className="size-4" />
        {FEEDBACK_MOCK_COPY.button}
      </Button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4 sm:p-8">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            // 공통 모달과 같은 황금비 규칙(좁음 400px, 여백 20/32px, 사이 20px).
            className="w-full max-w-[25rem] space-y-group rounded-xl border bg-card p-group shadow-lg sm:p-block"
          >
            <h2 id={titleId} className="text-lg font-semibold">
              {FEEDBACK_MOCK_COPY.title}
            </h2>
            <p className="text-sm leading-6 text-muted-foreground">{FEEDBACK_MOCK_COPY.body}</p>
            {context && <p className="text-xs text-muted-foreground">대상 화면: {context}</p>}
            <div className="flex justify-end">
              <Button ref={closeRef} onClick={close}>
                {FEEDBACK_MOCK_COPY.close}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
