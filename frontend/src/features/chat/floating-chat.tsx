/*
 * 담당: [A] | 책임: 첫 화면·/ai를 뺀 모든 화면(체크리스트·절차 상세 등) 위에 여닫는 플로팅 AI 대화창(은행 상담 채팅 방식)과 /ai 전체 대화 화면.
 * 근거: UI 전면 개편 지시서 3장(P0 체크리스트 → AI 채팅 연결, 모바일 첫 뷰포트에 대화·질문창).
 * 구현: 대화 부품은 HomeChatWindow 하나를 그대로 쓴다(variant만 다름). 새 대화 기능·API를 만들지 않는다.
 *   - 플로팅 창은 닫아도 그리기를 멈추지 않고 숨기기만 한다 → 다시 열면 대화·입력이 그대로다(체크리스트도 뒤에 그대로).
 *   - 닫기: 바깥(뒤쪽 투명 막) 누르기 · 위쪽 [닫기] · Esc. 닫으면 초점은 플로팅 버튼으로 돌아간다.
 *     창 안에 확인창·저장 설정 모달이 떠 있으면 Esc는 그 모달만 닫는다.
 *   - 데스크톱: 오른쪽 아래 패널. 모바일(768px 미만): 아래에서 올라오는 시트(화면 높이 85%).
 *   - 페이지 이동 기록(history)을 쌓지 않아 휴대폰 뒤로 가기는 전과 같이 이전 화면으로 간다.
 *   추가 수정 지시서 3장 + 사용자 지시(2026-10-30): 오른쪽 아래 플로팅 내비게이션 한 묶음 — 위에서부터
 *   [저장](저장 설정 창) · [AI 질문] · [체크리스트]. 세 버튼은 크기·모양·그림자가 같고, 지금 화면 버튼은 색으로 표시만
 *   한다(aria-current, 크기·배치 그대로). 화면별 동작:
 *   - AI 질문: 첫 화면은 /ai로 이동, /ai는 지금 화면, 그 밖(체크리스트·절차 상세 등)은 플로팅 대화창을 연다.
 *   - 체크리스트: /checklist는 지금 화면, 답한 적이 있으면 /checklist로, 없으면 질문 3개(W-01) 창을 연다.
 * 제한사항: 저장 안 된(미동의) 대화는 다른 화면으로 이동하면 사라진다는 기존 규칙(S11·D-11)을 그대로 따른다.
 *   이동할 때 그 확인창이 뜨면 창을 다시 열어 보이게 한다.
 */
import { ListChecks, MessageCircle, Save } from "lucide-react"
import type { ReactNode, Ref } from "react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { useAuthStore } from "@/features/auth/auth-store"
import { useChecklistSaveModal } from "@/features/checklist/checklist-consent-band"
import { useServerChecklistStore } from "@/features/checklist/server-checklist"
import { ChecklistSaveModalHost } from "@/features/checklist/storage-settings"
import { useHandoffFlight } from "@/features/kakao/use-handoff"
import { cn } from "@/lib/utils"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"
import { HomeChatWindow } from "./home-chat-window"

const NAV_BUTTON_CLASS =
  "inline-flex size-14 flex-col items-center justify-center gap-0.5 rounded-full border shadow-lg outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50"

function NavButton({
  label,
  shortLabel,
  icon,
  current = false,
  onClick,
  buttonRef,
  expanded,
  hasPopup = false,
  attention = false,
}: {
  label: string
  shortLabel: string
  icon: ReactNode
  current?: boolean
  onClick?: () => void
  buttonRef?: Ref<HTMLButtonElement>
  expanded?: boolean
  hasPopup?: boolean
  // 확인이 필요한 일이 있을 때(예: 서버 기록 선택) 오른쪽 위 작은 점. 이름에도 함께 알린다.
  attention?: boolean
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      aria-label={attention ? `${label}, 확인 필요` : label}
      title={attention ? `${label} · 확인 필요` : label}
      aria-current={current ? "page" : undefined}
      aria-expanded={expanded}
      aria-haspopup={hasPopup ? "dialog" : undefined}
      disabled={current}
      onClick={onClick}
      className={cn(
        NAV_BUTTON_CLASS,
        "relative",
        current
          ? "border-primary bg-primary text-primary-foreground"
          : "border-primary/20 bg-card text-primary hover:bg-accent",
      )}
    >
      {attention && (
        <span
          aria-hidden
          className="absolute top-0.5 right-0.5 size-3 rounded-full border-2 border-card bg-danger-foreground"
        />
      )}
      {icon}
      <span aria-hidden className="text-[10px] font-semibold leading-none">
        {shortLabel}
      </span>
    </button>
  )
}

// 오른쪽 아래 플로팅 내비게이션(모든 화면). 대화창을 띄울 수 있는 화면에서는 플로팅 대화창도 함께 그린다.
// sidebarCollapsed: 데스크톱 사이드바 폭(16rem/4rem)과 본문 최대 폭(5xl/6xl)을 앱 레이아웃과 똑같이 맞추려고 받는다.
export function FloatingNav({ sidebarCollapsed = false }: { sidebarCollapsed?: boolean }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  const openOverlay = useOverlayStore((s) => s.open)
  const openSaveModal = useChecklistSaveModal((s) => s.setOpen)
  // 로그인 계정에 고르지 않은 서버 기록이 있으면(새 기기 등) [저장]에 확인 필요 점을 띄운다.
  const accountId = useAuthStore((s) => s.accountId)
  const serverChoicePending = useServerChecklistStore(
    (s) => s.pending !== null && accountId !== null && s.accountId === accountId,
  )
  const chatPanel = pathname !== "/" && pathname !== "/ai"
  const [open, setOpen] = useState(false)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const close = useCallback(() => {
    setOpen(false)
    launcherRef.current?.focus()
  }, [])
  const reopen = useCallback(() => setOpen(true), [])

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      // 창 안의 확인창·모달(role="dialog"/"alertdialog")이 먼저 닫히게 둔다.
      if (panelRef.current?.querySelector('[role="dialog"], [role="alertdialog"]')) return
      close()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close])

  const onAi = () => {
    if (chatPanel) setOpen((value) => !value)
    else navigate("/ai")
  }
  // 카카오 인계 답을 받는 중이면 질문 3개 대신 체크리스트(스켈레톤)로 간다.
  const handoffInFlight = useHandoffFlight((s) => s.inFlight)
  const onChecklist = () =>
    hasAnswers || handoffInFlight ? navigate("/checklist") : openOverlay("start")

  return (
    <>
      {/* 오른쪽 아래 한 묶음. 휴대폰 안전 영역 위, 56px(터치 44px 이상). 움직이는 효과는 두지 않는다. */}
      {/* 추가 개선 지시서 2장: 본문(main)과 같은 칸(사이드바 오른쪽, 같은 최대 폭·좌우 여백)을 고정 틀로 겹쳐 두고
          그 오른쪽 끝에 붙여, 버튼 묶음의 오른쪽 끝이 본문 오른쪽 정렬선과 같다. 아래는 바닥글 선(64px) 위로 16px 띄운다. */}
      <div
        className={cn(
          "pointer-events-none fixed inset-x-0 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-40",
          sidebarCollapsed ? "md:left-16" : "md:left-64",
          open && "max-md:hidden",
        )}
      >
        <div
          className={cn(
            // 본문 칸과 같은 상자. 768px 이상은 본문 오른쪽 여백(88px) 안, 상자 끝에서 16px 안쪽에 버튼을 둔다
            // → 본문 끝과 버튼 사이 16px. 모바일은 화면 오른쪽 끝 가까이에 떠 있다(본문을 조금 가려도 됨).
            "mx-auto flex w-full justify-end px-3 sm:px-5 md:pr-4",
            sidebarCollapsed ? "max-w-6xl" : "max-w-5xl",
          )}
        >
          <nav aria-label="빠른 이동" className="pointer-events-auto flex flex-col gap-2">
            <NavButton
              label="저장 설정"
              attention={serverChoicePending}
              shortLabel="저장"
              icon={<Save className="size-5" aria-hidden />}
              hasPopup
              onClick={() => openSaveModal(true)}
            />
            <NavButton
              label="AI에게 질문하기"
              shortLabel="AI 질문"
              icon={<MessageCircle className="size-5" aria-hidden />}
              current={pathname === "/ai"}
              hasPopup={chatPanel}
              expanded={chatPanel ? open : undefined}
              buttonRef={launcherRef}
              onClick={onAi}
            />
            <NavButton
              label="절차 체크리스트"
              shortLabel="체크리스트"
              icon={<ListChecks className="size-5" aria-hidden />}
              current={pathname === "/checklist"}
              onClick={onChecklist}
            />
          </nav>
        </div>
      </div>
      {/* 체크리스트 [저장]과 같은 저장 모달. 화면에 저장 띠가 있으면 띠가 그리고, 없으면 여기서 그린다. */}
      <ChecklistSaveModalHost />
      {chatPanel && (
        <>
          {/* 바깥 영역: 누르면 닫힌다. 체크리스트가 비쳐 보이도록 아주 옅게만 덮는다. */}
          <div
            aria-hidden
            className={cn("fixed inset-0 z-40 bg-overlay/20", !open && "hidden")}
            onClick={close}
          />
          <div
            ref={panelRef}
            role="dialog"
            aria-label="AI 대화창"
            hidden={!open}
            className={cn(
              "fixed z-50 overflow-hidden border bg-card shadow-2xl",
              // 모바일: 아래 시트. 키보드가 열려도 dvh 기준이라 질문창이 보인다.
              // 높이는 대화창이 정한다(대화 없으면 내용만큼, 있으면 85%). 위로는 화면 85%를 넘지 않는다.
              "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl pb-[env(safe-area-inset-bottom)]",
              // 데스크톱: 오른쪽 아래 패널(버튼 위)
              "md:inset-x-auto md:right-24 md:bottom-20 md:max-h-[min(40rem,calc(100dvh-7rem))] md:w-[26rem] md:rounded-2xl md:pb-0",
              !open && "hidden",
            )}
          >
            <HomeChatWindow
              variant="floating"
              onClose={close}
              closeButtonRef={closeRef}
              onBlocked={reopen}
            />
          </div>
        </>
      )}
    </>
  )
}

// /ai 전체 대화 화면: 첫 화면 [AI 채팅] 카드의 목적지. 제목·소개를 두지 않고 대화 상자가 화면 높이를 채운다
// (모바일 첫 화면에서 질문창이 바로 보이게). 768px 미만은 오른쪽을 플로팅 내비게이션 자리로 비워 질문창을 가리지 않는다
// (768px 이상은 앱 레이아웃이 본문 옆 여백을 이미 비워 둔다). 위쪽 줄 높이(모바일 3.5rem)와 본문 여백을 뺀 높이다.
export function AiChatPage() {
  return (
    // 높이: 본문 위아래 여백(모바일 32px·데스크톱 56px)을 음수 여백으로 16px·32px까지 줄이고 남은 화면을 채운다.
    <div className="-my-4 h-[calc(100dvh-5.5rem)] pr-16 sm:pr-[4.75rem] md:-my-6 md:h-[calc(100dvh-4rem)] md:pr-0">
      <h1 className="sr-only">AI에게 질문하기</h1>
      <HomeChatWindow variant="page" />
    </div>
  )
}
