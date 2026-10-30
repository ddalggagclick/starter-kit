/*
 * 담당: [A] | 책임: 공통 모달(저장 설정 D-03 등). 근거: 디자인 시스템 v1.0 1장(부품 조립)·7.4(모달)·9장(접근성).
 * 구현: Modal → Modal.Header(제목·부제) → Modal.Body(내용) → Modal.Actions(버튼) 순으로 조립하고, 열고 닫는 상태는 부모가 관리한다.
 *   열리면 모달 안 첫 입력·버튼으로 초점을 옮기고, Tab·Shift+Tab은 모달 안에서만 돈다(초점 가두기).
 *   Esc 키나 바깥(어두운 배경)을 누르면 onClose를 부른다. 닫히면 모달을 열었던 요소로 초점을 돌려준다.
 *   포털 없이 그 자리에 그린다: 고정 위치(fixed)라 화면 전체를 덮고, 기존 화면 테스트가 띠(region) 안에서 버튼을 찾을 수 있다.
 *   황금비(사용자 지시 2026-10-30): 폭 3단계 — 좁음 25rem(400) · 기본 32rem(≈400×√φ) · 넓음 40.5rem(≈400×φ).
 *   안쪽 여백 모바일 group 20px · 데스크톱 block 32px(비율 1.6), 머리·본문·버튼 사이 group 20px, 본문 항목 사이 12px,
 *   바깥 여백 16/32px, 모서리 14px(디자인 시스템 v1.0 7.4·5.2). 닫기(X)는 여백÷φ 위치(12/20px)에 둔다(쓰는 쪽).
 * 제한사항: 모달을 여러 겹 띄우지 않는다(7.4). 입력 중 닫기 확인이 필요하면 쓰는 쪽에서 처리한다.
 *   기존 확인창(ConfirmDialog)은 그대로 두고, 이 부품으로 옮기는 일은 후속 "공통 부품 정리"에서 한다(#197 범위 밖).
 */
import { createContext, type ReactNode, useContext, useEffect, useId, useRef } from "react"
import { cn } from "@/lib/utils"

// 모달 안에서 초점을 받을 수 있는 요소
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Modal.Header의 제목을 대화상자 이름(aria-labelledby)으로 잇기 위한 id
const TitleIdContext = createContext<string | undefined>(undefined)

// #227: className으로 넓은 모달·왼쪽 서랍 모양을 덧붙이고, 제목(Modal.Header)이 없는 창은 label로 이름을 붙인다.
function ModalRoot({
  onClose,
  children,
  className,
  label,
}: {
  onClose: () => void
  children: ReactNode
  className?: string
  label?: string
}) {
  const titleId = useId()
  const dialog = useRef<HTMLDivElement>(null)
  // 부모가 매번 새 함수를 넘겨도 초점 이동·키 처리를 다시 걸지 않도록 최신 onClose만 기억한다.
  const closeRef = useRef(onClose)
  useEffect(() => {
    closeRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusables = () =>
      Array.from(dialog.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
    ;(focusables()[0] ?? dialog.current)?.focus()

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeRef.current()
        return
      }
      if (event.key !== "Tab") return
      const items = focusables()
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      // 초점이 모달 밖에 있거나 끝에 닿으면 반대쪽 끝으로 돌린다.
      if (!dialog.current?.contains(active)) {
        event.preventDefault()
        first.focus()
      } else if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      // 저장 등으로 연 버튼이 화면에서 사라졌으면 돌려줄 곳이 없으니 건너뛴다.
      if (opener?.isConnected) opener.focus()
    }
  }, [])

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: 바깥 누르기 닫기는 마우스용 보조 동작이고, 키보드는 Esc로 닫는다(9장).
    // biome-ignore lint/a11y/useKeyWithClickEvents: 키보드 닫기는 위 keydown(Esc)에서 처리한다.
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 sm:p-8"
      onClick={(event) => {
        if (event.target === event.currentTarget) closeRef.current()
      }}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={label ? undefined : titleId}
        aria-label={label}
        tabIndex={-1}
        className={cn(
          "max-h-[calc(100dvh-2rem)] w-full max-w-[32rem] space-y-group overflow-y-auto rounded-xl border bg-card p-group text-card-foreground shadow-lg outline-none sm:max-h-[calc(100dvh-4rem)] sm:p-block",
          className,
        )}
      >
        <TitleIdContext.Provider value={titleId}>{children}</TitleIdContext.Provider>
      </div>
    </div>
  )
}

function ModalHeader({ title, subtitle }: { title: ReactNode; subtitle?: ReactNode }) {
  const titleId = useContext(TitleIdContext)
  return (
    <div className="space-y-2">
      <h2 id={titleId} className="text-lg font-semibold leading-snug">
        {title}
      </h2>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  )
}

function ModalBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("space-y-3 text-sm", className)}>{children}</div>
}

// #227: 버튼은 오른쪽 끝에 가로로 놓고, 주된 버튼([저장] 등)은 맨 오른쪽에 둔다(사용자 요청: 휴대폰에서도 같게).
//   좁아서 넘치면 다음 줄로 넘어가도 오른쪽 정렬을 지킨다. 높이는 Button 기본 40px.
function ModalActions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap justify-end gap-2">{children}</div>
}

export const Modal = Object.assign(ModalRoot, {
  Header: ModalHeader,
  Body: ModalBody,
  Actions: ModalActions,
})
