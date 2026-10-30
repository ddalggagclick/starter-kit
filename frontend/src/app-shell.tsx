/*
 * 담당: [A] | 책임: 앱 공통 틀 — 왼쪽 사이드바(데스크톱), 위쪽 줄과 메뉴 서랍(모바일), 화면 위에 여는 안내 모달.
 * 근거: #227 새 시안 https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu (사용자 지시: 이 시안대로 화면 전부 변경).
 * 구현:
 *   - 헤더 메뉴를 왼쪽 사이드바로 옮겼다. [체크리스트]는 페이지로 가고, [전체 절차]·[상속 관계]·[상속세]는 지금 화면 위
 *     모달로 연다(페이지 이동이 없어 첫 화면 대화가 끊기지 않는다). 사이드바는 접으면 아이콘 줄만 남는다.
 *   - 아래쪽 계정 칸: 로그인 전 [로그인], 로그인 뒤 이메일·[로그아웃]·회원 탈퇴(기존 헤더와 같은 동작).
 *   - 768px 미만: 사이드바를 숨기고 위쪽 줄의 [메뉴 열기]로 왼쪽 서랍을 연다.
 *   - 모달 안 내용은 기존 화면 부품(RelationshipGuidePage·TaxGuidePage·InitialQuestionsPage·로그인 등)을 그대로
 *     써서 기능이 바뀌지 않는다. [전체 절차]는 시안대로 펼쳐 보기(ProcedureSteps). 부품은 InOverlayContext로 모달 안임을
 *     알고 이동 대신 모달을 닫거나 바꾼다. 모달 안 링크를 누르면 모달을 먼저 닫고 이동한다(이탈 확인창이 가리지 않게).
 *   - [로그인]·회원 탈퇴도 모달로 연다(로그인 ↔ 회원가입 ↔ 비밀번호 재설정은 모달끼리 바뀐다).
 *   - 기존 주소(/checklist·/procedures·/guide/*·/start·/login·/signup·/auth/forgot·/account/delete)는 그대로 열린다.
 * 제한사항: 사이드바 접힘 상태는 저장하지 않는다(새로고침하면 펼쳐진다).
 */
import {
  CircleCheck,
  ClipboardList,
  House,
  ListChecks,
  LogIn,
  LogOut,
  type LucideIcon,
  Menu,
  PanelLeft,
  Receipt,
  Users,
  UserX,
  X,
} from "lucide-react"
import type { MouseEvent, ReactNode } from "react"
import { Link, useLocation } from "react-router"
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"
import { AccountDeletePage } from "@/features/auth/account-delete-page"
import { logoutRequest } from "@/features/auth/auth-api"
import { useAuthStore } from "@/features/auth/auth-store"
import { ForgotPasswordPage } from "@/features/auth/forgot-password-page"
import { LoginPage } from "@/features/auth/login-page"
import { SignupPage } from "@/features/auth/signup-page"
import { EntryGateway } from "@/features/checklist/entry-gateway"
import { InitialQuestionsPage } from "@/features/checklist/initial-questions-page"
import { useServerChecklistStore } from "@/features/checklist/server-checklist"
import { RelationshipModal, TaxModal } from "@/features/law/guide-modals"
import { ProcedureSteps } from "@/features/procedures/procedure-steps"
import { cn } from "@/lib/utils"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { InOverlayContext, type OverlayName, useOverlayStore } from "@/shared/state/overlay-store"

type MenuItem =
  | { kind: "page"; to: string; label: string; icon: LucideIcon }
  | { kind: "modal"; open: OverlayName; label: string; icon: LucideIcon }

// 시안 메뉴 4개 + [홈](사용자 요청 2026-10-29: 사이드바에서 첫 화면으로 가기). [AI 질문]은 대화창이 첫 화면에 있어 넣지 않는다.
const MENU: readonly MenuItem[] = [
  { kind: "page", to: "/", label: "홈", icon: House },
  { kind: "page", to: "/checklist", label: "체크리스트", icon: ListChecks },
  { kind: "modal", open: "steps", label: "전체 절차", icon: ClipboardList },
  { kind: "modal", open: "relation", label: "상속 관계", icon: Users },
  { kind: "modal", open: "tax", label: "상속세", icon: Receipt },
]

// 시안 메뉴 항목: 높이 40px, 글자 16px, 아이콘 18px
const ITEM_CLASS =
  "flex h-10 w-full items-center gap-3 rounded-md px-3 text-left text-base outline-none max-md:min-h-11 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"

// 접힌 사이드바에서는 글자를 화면에서만 감춘다(sr-only). 화면낭독기는 메뉴 이름을 계속 읽는다.
function Label({ collapsed, children }: { collapsed: boolean; children: ReactNode }) {
  return <span className={collapsed ? "sr-only" : "truncate"}>{children}</span>
}

function MenuList({ collapsed = false, onPicked }: { collapsed?: boolean; onPicked?: () => void }) {
  const open = useOverlayStore((s) => s.open)
  const { pathname } = useLocation()
  // 최신 시안: 아직 답하지 않았으면 [체크리스트]는 페이지 대신 질문 3개 모달을 연다(답하면 체크리스트로 간다).
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  // 로그인 사용자의 서버 기록을 불러올 수 있으면 체크리스트 화면(불러오기 선택)으로 보낸다.
  const serverPending = useServerChecklistStore((s) => s.pending !== null)
  return (
    <nav aria-label="주요 메뉴" className="flex flex-col gap-1 px-2">
      {MENU.map((item) => {
        const Icon = item.icon
        const icon = <Icon className="size-[18px] shrink-0" aria-hidden />
        const itemClass = cn(ITEM_CLASS, collapsed && "mx-auto w-10 justify-center gap-0 px-0")
        if (item.kind === "page") {
          // 홈은 첫 화면에서만, 체크리스트는 절차 상세(/procedures/p01 등)에서도 선택 표시한다.
          const active =
            item.to === "/checklist"
              ? pathname === "/checklist" || pathname.startsWith("/procedures/")
              : pathname === item.to
          return (
            <Link
              key={item.label}
              to={item.to}
              title={item.label}
              onClick={(event) => {
                onPicked?.()
                // 답하기 전 [체크리스트]만 질문 모달로 바꾼다([홈]은 그대로 이동).
                if (item.to === "/checklist" && !hasAnswers && !serverPending) {
                  event.preventDefault()
                  open("start")
                }
              }}
              aria-current={active ? "page" : undefined}
              className={cn(itemClass, active && "bg-accent font-semibold text-accent-foreground")}
            >
              {icon}
              <Label collapsed={collapsed}>{item.label}</Label>
            </Link>
          )
        }
        return (
          <button
            key={item.label}
            type="button"
            title={item.label}
            aria-haspopup="dialog"
            className={itemClass}
            onClick={() => {
              onPicked?.()
              open(item.open)
            }}
          >
            {icon}
            <Label collapsed={collapsed}>{item.label}</Label>
          </button>
        )
      })}
    </nav>
  )
}

// 계정 칸(계정 관리 UI 개선 지시서): 기존 로그인·로그아웃·회원 탈퇴 동작 그대로, 모양만 나눈다.
//   구분선(border-t)은 로그인 전후 모두 바닥에서 64px 위(바닥글 선과 같은 높이)에 고정한다.
//   - 로그인 전: 선 아래 64px 칸에 네이비 [로그인]만(기존).
//   - 로그인 후: 선 위에 "✓ 로그인 중"(+ 메일 주소)과 전체 너비 [로그아웃](44px 보조 버튼),
//     선 아래 64px 칸 오른쪽에 주의 색 [회원 탈퇴](14px 글자 버튼, 기존 확인 모달). 늘어난 내용은 선 위로 쌓여
//     선과 위쪽 메뉴가 움직이지 않는다. 프로필 사진·편집은 없다(기능 없음).
//   - 사이드바를 접으면 같은 자리에 아이콘 버튼(로그아웃·회원 탈퇴)으로 보인다.
//   - 사용자 지시: 웹(사이드바)에서는 "로그인 중"·메일 표시를 생략하고, 모바일 메뉴 서랍(drawer)에서만 보인다.
//     모바일에서는 [회원 탈퇴]를 [로그아웃]과 같은 가운데 정렬로 둔다(아이콘 세로줄 맞춤).
function AccountArea({
  collapsed = false,
  onPicked,
  drawer = false,
}: {
  collapsed?: boolean
  onPicked?: () => void
  drawer?: boolean
}) {
  const open = useOverlayStore((s) => s.open)
  const accountId = useAuthStore((s) => s.accountId)
  const email = useAuthStore((s) => s.email)
  const signOut = useAuthStore((s) => s.signOut)
  // 서버 로그아웃 결과와 관계없이 화면은 로그아웃 상태로 바꾼다.
  const onSignOut = () => {
    void logoutRequest()
    signOut()
    onPicked?.()
  }
  const openOverlay = (name: "login" | "account-delete") => {
    onPicked?.()
    open(name)
  }
  const lineRow = cn(
    "flex h-16 shrink-0 items-center border-t px-3",
    collapsed && "justify-center px-2",
  )

  if (!accountId) {
    return (
      <div className={lineRow}>
        <Button
          type="button"
          className={cn("w-full", collapsed && "px-0")}
          title="로그인"
          aria-haspopup="dialog"
          onClick={() => openOverlay("login")}
        >
          <LogIn className="size-4" aria-hidden />
          <Label collapsed={collapsed}>로그인</Label>
        </Button>
      </div>
    )
  }

  return (
    <div>
      <div className={cn("space-y-3 px-3 pb-4", collapsed && "flex flex-col items-center px-2")}>
        {drawer && (
          <div className="space-y-0.5">
            <p
              role="status"
              className="flex items-center gap-1.5 text-sm font-semibold text-success-foreground"
            >
              <CircleCheck className="size-4 shrink-0" aria-hidden />
              로그인 중
            </p>
            {email && (
              <p className="truncate pl-[1.375rem] text-xs text-muted-foreground" title={email}>
                {email}
              </p>
            )}
          </div>
        )}
        <Button
          type="button"
          variant="outline"
          className={cn(
            "h-11 w-full border-primary/30 font-semibold text-primary hover:bg-accent",
            collapsed && "size-11 px-0",
          )}
          title="로그아웃"
          onClick={onSignOut}
        >
          <LogOut className="size-4" aria-hidden />
          <Label collapsed={collapsed}>로그아웃</Label>
        </Button>
      </div>
      {/* 웹: 오른쪽 정렬. 모바일 서랍: [로그아웃]과 같은 가운데 정렬. 접힌 사이드바: 가운데(아이콘만). */}
      <div className={cn(lineRow, drawer || collapsed ? "justify-center" : "justify-end")}>
        <button
          type="button"
          aria-haspopup="dialog"
          aria-label={collapsed ? "회원 탈퇴" : undefined}
          title="회원 탈퇴"
          onClick={() => openOverlay("account-delete")}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-sm font-medium text-danger-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <UserX className="size-4" aria-hidden />
          {!collapsed && "회원 탈퇴"}
        </button>
      </div>
    </div>
  )
}

// 사용자 지시(2026-10-30): 로고 이미지를 빼고 서비스 이름 글자만 둔다. 사이드바를 접으면 이름도 숨긴다(첫 화면은 [홈] 메뉴).
function Logo({ collapsed = false }: { collapsed?: boolean }) {
  if (collapsed) return null
  return (
    <Link
      to="/"
      className="flex min-w-0 items-center gap-2 font-semibold"
      aria-label="상속길잡이 첫 화면"
    >
      <span className="truncate">상속길잡이</span>
    </Link>
  )
}

// 데스크톱(768px 이상) 왼쪽 사이드바. 접으면 아이콘 줄(4rem)만 남는다.
export function SiteSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const toggleLabel = collapsed ? "사이드바 펼치기" : "사이드바 접기"
  return (
    <aside
      aria-label="사이드바"
      className="sticky top-0 hidden h-svh flex-col overflow-hidden border-r bg-background md:flex"
    >
      <div className={cn("flex items-center gap-2 p-4", collapsed && "flex-col px-0 py-3")}>
        <Logo collapsed={collapsed} />
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={toggleLabel}
          title={toggleLabel}
          className={cn(
            "inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            !collapsed && "ml-auto",
          )}
        >
          <PanelLeft className="size-4" aria-hidden />
        </button>
      </div>
      <MenuList collapsed={collapsed} />
      {/* 계정 칸은 맨 아래. 구분선은 로그인 전후 모두 바닥에서 64px 위라 바닥글 선과 늘 같은 수평선이다. */}
      <div className="mt-auto">
        <AccountArea collapsed={collapsed} />
      </div>
    </aside>
  )
}

// 모바일(768px 미만) 위쪽 줄: [메뉴 열기] · 로고 · 로그인/로그아웃.
export function MobileTopBar() {
  const open = useOverlayStore((s) => s.open)
  const menuOpen = useOverlayStore((s) => s.current === "menu")
  const accountId = useAuthStore((s) => s.accountId)
  const signOut = useAuthStore((s) => s.signOut)
  return (
    <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b bg-card px-3 py-1.5 md:hidden">
      <button
        type="button"
        aria-label="메뉴 열기"
        aria-haspopup="dialog"
        aria-expanded={menuOpen}
        onClick={() => open("menu")}
        className="inline-flex size-11 items-center justify-center rounded-md hover:bg-accent"
      >
        <Menu className="size-5" aria-hidden />
      </button>
      <Logo />
      {accountId ? (
        <Button
          variant="outline"
          size="sm"
          className="h-9"
          onClick={() => {
            void logoutRequest()
            signOut()
          }}
        >
          <LogOut className="size-4" aria-hidden />
          로그아웃
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          className="h-9"
          aria-haspopup="dialog"
          onClick={() => open("login")}
        >
          <LogIn className="size-4" aria-hidden />
          로그인
        </Button>
      )}
    </div>
  )
}

// narrow: 인증 모달은 시안처럼 좁게(25rem) 그리고 여백을 넓게 둔다.
const GUIDES: Record<
  Exclude<OverlayName, "menu">,
  { label: string; body: () => ReactNode; narrow?: boolean; wide?: boolean; className?: string }
> = {
  steps: { label: "전체 절차", body: () => <ProcedureSteps /> },
  relation: { label: "상속 관계", body: () => <RelationshipModal /> },
  tax: { label: "상속세", body: () => <TaxModal /> },
  start: { label: "상속 절차 시작", body: () => <InitialQuestionsPage />, wide: true },
  login: { label: "로그인", body: () => <LoginPage />, narrow: true },
  signup: { label: "회원가입", body: () => <SignupPage />, narrow: true },
  forgot: { label: "비밀번호 재설정", body: () => <ForgotPasswordPage />, narrow: true },
  "account-delete": { label: "회원 탈퇴", body: () => <AccountDeletePage />, narrow: true },
  // 처음 들어올 때 첫 화면 위 진입 선택 창(추가 개선 지시서 1장: 폭 640px, 안쪽 여백 넓게)
  entry: {
    label: "시작 방법 선택",
    body: () => <EntryGateway />,
    className: "max-w-[40.5rem]",
  },
}

// 지금 열린 창 하나를 그린다. Esc·바깥 누르기·[닫기]로 닫히고, 닫히면 연 버튼으로 초점이 돌아간다(Modal 부품).
export function AppOverlays() {
  const current = useOverlayStore((s) => s.current)
  const close = useOverlayStore((s) => s.close)
  if (!current) return null

  // 창 안의 링크로 다른 화면에 갈 때는 창을 먼저 닫는다(이탈 확인창이 창에 가리지 않게).
  const closeOnLink = (event: MouseEvent) => {
    if ((event.target as HTMLElement).closest("a[href]")) close()
  }

  if (current === "menu") {
    return (
      <Modal
        onClose={close}
        label="메뉴"
        className="fixed inset-y-0 left-0 max-h-none w-[85%] max-w-xs space-y-0 rounded-none border-r p-0 sm:max-h-none sm:p-0"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-2 p-3">
            <Logo />
            <button
              type="button"
              aria-label="메뉴 닫기"
              onClick={close}
              className="inline-flex size-11 items-center justify-center rounded-md hover:bg-accent"
            >
              <X className="size-5" aria-hidden />
            </button>
          </div>
          <MenuList onPicked={close} />
          <div className="mt-auto">
            <AccountArea onPicked={close} drawer />
          </div>
        </div>
      </Modal>
    )
  }

  const guide = GUIDES[current]
  return (
    // key: 로그인 → 회원가입처럼 모달 내용이 바뀌면 새 창으로 다시 그려 첫 입력칸으로 초점을 옮긴다.
    <Modal
      key={current}
      onClose={close}
      label={guide.label}
      // 시안 크기: 기본 576px, 질문 3개 672px, 인증 400px(여백 넓게)
      className={cn(
        "relative",
        // 황금비 폭 3단계: 좁음 400 · 기본 512 · 넓음 648px(여백은 공통 모달 규칙).
        guide.className ??
          (guide.narrow ? "max-w-[25rem]" : guide.wide ? "max-w-[40.5rem]" : "max-w-[32rem]"),
      )}
    >
      <button
        type="button"
        aria-label="닫기"
        onClick={close}
        // 닫기 위치 = 안쪽 여백 ÷ φ(모바일 12px · 데스크톱 20px). 누르는 영역 36px.
        className="absolute top-3 right-3 inline-flex size-9 items-center justify-center rounded-md opacity-70 transition-opacity hover:bg-accent hover:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:top-5 sm:right-5"
      >
        <X className="size-4" aria-hidden />
      </button>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: 링크를 누르면 창을 닫는 보조 처리다. 링크 자체는 키보드로도 동작한다. */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: 키보드 Enter도 링크 click 이벤트로 들어온다. */}
      <div onClick={closeOnLink}>
        <InOverlayContext.Provider value={true}>{guide.body()}</InOverlayContext.Provider>
      </div>
    </Modal>
  )
}
