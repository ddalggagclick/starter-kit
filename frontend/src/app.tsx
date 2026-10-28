/**
 * 책임: [A] 앱 화면·라우팅 조립과 공통 레이아웃(전역 헤더·바닥글).
 * PRD: 간트 1구간 V1(04·05·06·10·13), 태스크 2-1-4(W-00~W-08 흐름 연결), 5-6-1(헤더 로그인 진입).
 * 구현할 기능: W-00 / W-01 / W-02 / W-03 / W-04 / W-05 / W-06 / W-07 / W-09(로그인) 경로와
 *   TanStack Query·React Router 제공자. 모든 화면 헤더에 로그인 버튼을 둔다.
 * 코드 경계: 화면 내용은 features/*에 둔다. 법적 판단·추천 규칙은 서버 책임이다.
 * 완료 기준: npm run dev/build, 각 경로가 화면을 렌더링한다.
 * 제한사항: 데이터는 V1 Mock이 기본이다(shared/api/data-source.ts). 실구현 시연으로 표기하지 않는다.
 * #211: 페이지 수를 줄이려고 AI 질문 페이지(/ai)를 첫 화면 대화창(id="ai")으로 합쳤다. /ai로 오면 /#ai로 보내고,
 *   헤더 [AI 질문]도 /#ai로 간다. 주소에 #이 있으면 그 위치로 화면을 내린다.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Compass, LogIn, LogOut } from "lucide-react"
import { useEffect, useState } from "react"
import {
  createBrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  type RouteObject,
  RouterProvider,
  useLocation,
} from "react-router"
import { Button } from "@/components/ui/button"
import { AccountDeletePage } from "@/features/auth/account-delete-page"
import { logoutRequest } from "@/features/auth/auth-api"
import { useAuthStore } from "@/features/auth/auth-store"
import { ForgotPasswordPage } from "@/features/auth/forgot-password-page"
import { LoginPage } from "@/features/auth/login-page"
import { ResetPasswordPage } from "@/features/auth/reset-password-page"
import { SignupPage } from "@/features/auth/signup-page"
import { useSessionRestore } from "@/features/auth/use-session-restore"
import { VerifyEmailPage } from "@/features/auth/verify-email-page"
import { ChecklistPage } from "@/features/checklist/checklist-page"
import { InitialQuestionsPage } from "@/features/checklist/initial-questions-page"
import { LandingPage } from "@/features/checklist/landing-page"
import { useServerChecklistSync } from "@/features/checklist/server-checklist"
import { useChecklistPersistence } from "@/features/checklist/use-checklist-persistence"
import { RelationshipGuidePage, TaxGuidePage } from "@/features/law/guide-page"
import { ProcedureDetailPage } from "@/features/procedures/procedure-detail"
import { ProceduresPage } from "@/features/procedures/procedures-page"
import { FeedbackMockButton } from "@/features/reports/feedback-mock-dialog"
import { cn } from "@/lib/utils"
import { LEGAL_DISCLAIMER } from "@/shared/content/checklist"

const NAV_ITEMS = [
  { to: "/checklist", label: "체크리스트" },
  { to: "/procedures", label: "전체 절차" },
  // AI 질문은 첫 화면 대화창 위치다(#211).
  { to: "/#ai", label: "AI 질문" },
  { to: "/guide/relationship", label: "상속 관계" },
  { to: "/guide/tax", label: "상속세" },
] as const

const NAV_LINK_CLASS = "whitespace-nowrap rounded-md px-3 py-1.5 text-sm hover:bg-muted"
const NAV_ACTIVE_CLASS = "bg-secondary font-semibold"

function SiteHeader() {
  const location = useLocation()
  const accountId = useAuthStore((s) => s.accountId)
  const email = useAuthStore((s) => s.email)
  const signOut = useAuthStore((s) => s.signOut)
  // 서버 로그아웃 결과와 관계없이 화면은 로그아웃 상태로 바꾼다.
  const onSignOut = () => {
    void logoutRequest()
    signOut()
  }
  return (
    <header className="border-b bg-card/80">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-bold">
          <span className="rounded-lg bg-primary p-1.5 text-primary-foreground">
            <Compass className="size-4" aria-hidden />
          </span>
          상속길잡이
        </Link>
        <div className="flex items-center gap-2">
          {accountId ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {email ?? "로그인됨"}
              </span>
              <Button variant="outline" size="sm" onClick={onSignOut}>
                <LogOut className="size-4" />
                로그아웃
              </Button>
              <Link to="/account/delete" className="text-xs text-muted-foreground underline">
                회원 탈퇴
              </Link>
            </>
          ) : (
            <Button asChild variant="outline" size="sm">
              <Link to="/login">
                <LogIn className="size-4" />
                로그인
              </Link>
            </Button>
          )}
        </div>
        <nav
          aria-label="주요 메뉴"
          className="-mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto"
        >
          {NAV_ITEMS.map((item) => {
            // # 위치 메뉴(/#ai)는 NavLink가 첫 화면 전체를 선택으로 보므로, 주소의 #까지 같을 때만 선택 표시한다.
            if (item.to.includes("#")) {
              const active = `${location.pathname}${location.hash}` === item.to
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={cn(NAV_LINK_CLASS, active && NAV_ACTIVE_CLASS)}
                >
                  {item.label}
                </Link>
              )
            }
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => cn(NAV_LINK_CLASS, isActive && NAV_ACTIVE_CLASS)}
              >
                {item.label}
              </NavLink>
            )
          })}
        </nav>
      </div>
    </header>
  )
}

function AppLayout() {
  // 새로고침 후 Refresh 쿠키로 로그인 상태를 복구한다(실제 Backend 모드만).
  useSessionRestore()
  // 동의한 경우에만 체크리스트를 이 기기에 저장·복원한다(4-2-1). 어느 화면에서 바꿔도 저장되도록 레이아웃에서 시작한다.
  useChecklistPersistence()
  // 로그인 사용자의 서버 체크리스트 저장(A17). 비로그인이면 요청하지 않는다.
  useServerChecklistSync()
  // 주소에 #이 있으면(예: /#ai) 그 위치로 화면을 내린다. 같은 주소를 다시 눌러도 내리도록 이동마다(key) 실행한다(#211).
  // 메일 인증 링크처럼 # 뒤가 위치가 아닌 경우에는 찾는 요소가 없어 아무것도 하지 않는다.
  const { hash, key } = useLocation()
  // biome-ignore lint/correctness/useExhaustiveDependencies: key는 같은 #로 다시 이동했을 때도 실행하려고 둔다.
  useEffect(() => {
    if (!hash) return
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.({ block: "start" })
  }, [hash, key])
  return (
    <div className="flex min-h-svh flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <Outlet />
      </main>
      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4 text-xs text-muted-foreground sm:px-6">
          <p>
            {/* Mock 표시(" · V1 Mock 데이터 사용 중…")는 사용자 요청으로 없앴다(#205). */}
            {LEGAL_DISCLAIMER}. 안내 문구·기한은 검수 전 예시입니다.
          </p>
          <FeedbackMockButton context="공통" />
        </div>
      </footer>
    </div>
  )
}

function NotFoundPage() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">페이지를 찾을 수 없습니다</h1>
      <Link to="/" className="underline underline-offset-4">
        첫 화면으로
      </Link>
    </div>
  )
}

export const appRoutes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "start", element: <InitialQuestionsPage /> },
      { path: "checklist", element: <ChecklistPage /> },
      { path: "procedures", element: <ProceduresPage /> },
      { path: "procedures/:procedureId", element: <ProcedureDetailPage /> },
      { path: "guide/relationship", element: <RelationshipGuidePage /> },
      { path: "guide/tax", element: <TaxGuidePage /> },
      // 예전 주소·즐겨찾기용. 뒤로 가기 반복이 없도록 기록을 바꿔치기(replace)한다(#211).
      { path: "ai", element: <Navigate to="/#ai" replace /> },
      { path: "login", element: <LoginPage /> },
      { path: "signup", element: <SignupPage /> },
      // 메일 링크 화면. 토큰은 # 뒤에 온다(팀원 요청).
      { path: "auth/verify", element: <VerifyEmailPage /> },
      { path: "auth/reset", element: <ResetPasswordPage /> },
      { path: "auth/forgot", element: <ForgotPasswordPage /> },
      { path: "account/delete", element: <AccountDeletePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]

export const createQueryClient = () =>
  new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })

export default function App() {
  const [router] = useState(() => createBrowserRouter(appRoutes))
  const [queryClient] = useState(createQueryClient)
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
