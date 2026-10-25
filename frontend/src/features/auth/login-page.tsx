/*
 * 담당: [A] | 책임: W-09 로그인 폼·오류 표시·로그인 상태 전환.
 * PRD: E5 / 스토리 5-2 / 태스크 5-2-1. API: A13 POST /api/auth/login (x-confirmed: true, 경로 제안).
 *   VITE_USE_MOCK_API=false면 실제 Backend로 로그인한다(auth-api.ts).
 * 구현: 빈 칸은 인라인 오류, 401은 사유를 구분하지 않는 같은 문구, 429는 잠시 후 재시도 안내.
 * 완료 기준: 실패 시 로그인된 것처럼 보이지 않는다. 성공하면 헤더가 로그인 상태로 바뀐다.
 * 제한사항: 회원가입·이메일 인증·비밀번호 재설정은 2구간(간트 25·27)이다. 비밀번호를 저장하지 않는다.
 */
import { LogIn } from "lucide-react"
import { type FormEvent, useId, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Notice } from "@/components/ui/notice"
import { MOCK_ACCOUNT } from "@/mocks/mock-api"
import { toApiFailure } from "@/shared/api/api-error"
import { USE_MOCK_API } from "@/shared/api/data-source"
import { loginRequest } from "./auth-api"
import { useAuthStore } from "./auth-store"

type FieldErrors = { email?: string; password?: string }

const loginFailureMessage = (status: number): string => {
  if (status === 429) return "로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요."
  if (status === 401) return "이메일 또는 비밀번호를 확인해 주세요."
  return "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요."
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const signIn = useAuthStore((state) => state.signIn)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const emailErrorId = useId()
  const passwordErrorId = useId()
  // 다른 화면(예: AI 제한 S9)에서 왔으면 로그인 후 그 화면으로 돌아간다.
  const returnTo = (location.state as { from?: string } | null)?.from ?? "/"

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!email.trim()) errors.email = "이메일을 입력해 주세요."
    if (!password) errors.password = "비밀번호를 입력해 주세요."
    setFieldErrors(errors)
    setFormError(null)
    if (errors.email || errors.password) return
    setSubmitting(true)
    try {
      signIn(await loginRequest(email.trim(), password))
      navigate(returnTo, { replace: true })
    } catch (error) {
      setFormError(loginFailureMessage(toApiFailure(error).status))
      setPassword("")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>로그인</CardTitle>
          <CardDescription>
            로그인하지 않아도 체크리스트·절차 안내·AI 질문을 이용할 수 있습니다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            {formError && <Notice tone="danger">{formError}</Notice>}
            <div className="space-y-1.5">
              <label htmlFor="login-email" className="text-sm font-medium">
                이메일
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(fieldErrors.email)}
                aria-describedby={fieldErrors.email ? emailErrorId : undefined}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
              {fieldErrors.email && (
                <p id={emailErrorId} className="text-sm text-danger-foreground">
                  {fieldErrors.email}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <label htmlFor="login-password" className="text-sm font-medium">
                비밀번호
              </label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(fieldErrors.password)}
                aria-describedby={fieldErrors.password ? passwordErrorId : undefined}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
              {fieldErrors.password && (
                <p id={passwordErrorId} className="text-sm text-danger-foreground">
                  {fieldErrors.password}
                </p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              <LogIn className="size-4" />
              {submitting ? "로그인 중…" : "로그인"}
            </Button>
          </form>
          <div className="mt-4 space-y-2 text-sm text-muted-foreground">
            <p>회원가입·비밀번호 재설정은 준비 중입니다.</p>
            {USE_MOCK_API && (
              <p className="rounded-md bg-muted px-3 py-2 text-xs">
                Mock 로그인 · 실제 계정 연동 아님 — {MOCK_ACCOUNT.email} / {MOCK_ACCOUNT.password}
              </p>
            )}
            <Link to="/" className="underline underline-offset-4">
              로그인 없이 계속하기
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
