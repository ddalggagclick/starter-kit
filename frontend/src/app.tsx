/**
 * 책임: [A] 앱 화면·라우팅 조립과 공통 레이아웃(전역 헤더·바닥글).
 * PRD: 간트 1구간 V1(04·05·06·10·13), 태스크 2-1-4(W-00~W-08 흐름 연결), 5-6-1(헤더 로그인 진입).
 * 구현할 기능: W-00 / W-01 / W-02 / W-03 / W-04 / W-05 / W-06 / W-07 / W-09(로그인) 경로와
 *   TanStack Query·React Router 제공자. 모든 화면 헤더에 로그인 버튼을 둔다.
 * 코드 경계: 화면 내용은 features/*에 둔다. 법적 판단·추천 규칙은 서버 책임이다.
 * 완료 기준: npm run dev/build, 각 경로가 화면을 렌더링한다.
 * 제한사항: 데이터는 V1 Mock이 기본이다(shared/api/data-source.ts). 실구현 시연으로 표기하지 않는다.
 * #211: 페이지 수를 줄이려고 AI 질문 페이지(/ai)를 첫 화면 대화창(id="ai")으로 합쳤다. /ai로 오면 /#ai로 보내고,
 *   주소에 #이 있으면 그 위치로 화면을 내린다.
 * #227: 대화창이 첫 화면에 바로 보이므로 헤더 [AI 질문] 메뉴는 뺐다(새 시안 메뉴 4개).
 *   새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu)대로 위쪽 헤더를 왼쪽 사이드바로 바꿨다(app-shell.tsx).
 *   모바일은 위쪽 줄 + 메뉴 서랍. 전체 절차·상속 관계·상속세·시작 질문은 화면 위 모달로 연다. 기존 주소는 그대로 둔다.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect, useLayoutEffect, useState } from "react"
import {
  createBrowserRouter,
  Link,
  Navigate,
  Outlet,
  type RouteObject,
  RouterProvider,
  useLocation,
} from "react-router"
import { AppOverlays, MobileTopBar, SiteSidebar } from "@/app-shell"
import { AccountDeletePage } from "@/features/auth/account-delete-page"
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
import { useOverlayStore } from "@/shared/state/overlay-store"

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
  // 이동이 일어나면(같은 주소로 다시 가는 경우 포함) 열려 있던 모달·메뉴 서랍을 닫는다(#227).
  // 예: 질문 3개 모달에서 [체크리스트 확인] → /checklist로 이동 → 모달이 닫힌다.
  const closeOverlay = useOverlayStore((s) => s.close)
  // useLayoutEffect: 새 화면이 그려진 뒤 그 화면이 여는 모달(예: 체크리스트 진입 시 질문 3개)보다 먼저 닫히도록.
  // biome-ignore lint/correctness/useExhaustiveDependencies: 이동마다 바뀌는 key가 바뀔 때만 닫는다.
  useLayoutEffect(() => {
    closeOverlay()
  }, [key])
  // 데스크톱 사이드바 접기·펼치기(#227 시안). 저장하지 않는 화면 상태다.
  const [collapsed, setCollapsed] = useState(false)
  return (
    <div
      className={cn(
        "grid min-h-svh",
        collapsed ? "md:grid-cols-[4rem_minmax(0,1fr)]" : "md:grid-cols-[16rem_minmax(0,1fr)]",
      )}
    >
      <SiteSidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      <div className="flex min-w-0 flex-col">
        <MobileTopBar />
        <main
          className={cn(
            "mx-auto w-full flex-1 px-4 py-6 sm:px-7 sm:py-8",
            collapsed ? "max-w-6xl" : "max-w-5xl",
          )}
        >
          <Outlet />
        </main>
        {/* 최신 시안 바닥글: [정보 오류 제보]만 오른쪽에 둔다(사용자 지시로 안내 문장은 뺐다. 첫 화면·체크리스트 경고에 같은 뜻이 있다). */}
        <footer className="border-t">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-end gap-3 px-4 py-4 text-sm text-muted-foreground sm:px-7">
            <FeedbackMockButton context="공통" />
          </div>
        </footer>
      </div>
      <AppOverlays />
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
