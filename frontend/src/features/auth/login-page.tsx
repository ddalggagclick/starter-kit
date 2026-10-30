/*
 * 담당: [A] | 책임: W-09 로그인 폼·오류 표시·로그인 상태 전환.
 * PRD: E5 / 스토리 5-2 / 태스크 5-2-1. API: A13 POST /api/auth/login (x-confirmed: true, 경로 제안).
 *   VITE_USE_MOCK_API=false면 실제 Backend로 로그인한다(auth-api.ts).
 * 구현: 빈 칸은 인라인 오류, 401은 사유를 구분하지 않는 같은 문구, 429는 잠시 후 재시도 안내.
 * 완료 기준: 실패 시 로그인된 것처럼 보이지 않는다. 성공하면 헤더가 로그인 상태로 바뀐다.
 *   회원가입(/signup)·비밀번호 재설정(/auth/forgot)으로 가는 링크를 둔다. 이메일 인증 전 로그인(401)은 서버 안내 문구를 보인다.
 *   #227 새 시안: 사이드바 [로그인]은 지금 화면 위 모달로 연다. 모달에서 로그인하면 이동하지 않고 모달만 닫혀
 *   보던 화면(대화·체크리스트)이 그대로 남는다. 회원가입·비밀번호 재설정 링크는 그 모달로 바꾼다. /login 주소는 전과 같다.
 * 제한사항: 비밀번호를 저장하지 않는다.
 */
import { type FormEvent, useId, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { type ApiFailure, toApiFailure } from "@/shared/api/api-error"
import { useInOverlay, useOverlayStore } from "@/shared/state/overlay-store"
import { loginRequest } from "./auth-api"
import { AUTH_INPUT_CLASS, AuthCard, AuthLink, PasswordInput } from "./auth-form-field"
import { useAuthStore } from "./auth-store"

type FieldErrors = { email?: string; password?: string }

// 401은 계정 존재 여부를 드러내지 않는 같은 문구다. 다만 서버가 사람이 읽을 문장(이메일 인증 필요)을 주면 그대로 쓴다.
export const loginFailureMessage = ({ status, code, message }: ApiFailure): string => {
  if (status === 429) return "로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요."
  if (status === 401) {
    return message && message !== code ? message : "이메일 또는 비밀번호를 확인해 주세요."
  }
  return "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요."
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const signIn = useAuthStore((state) => state.signIn)
  const inOverlay = useInOverlay()
  const closeOverlay = useOverlayStore((s) => s.close)
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
      // 모달이면 보던 화면에 그대로 머문다. 페이지(/login)면 전처럼 온 곳으로 돌아간다.
      if (inOverlay) closeOverlay()
      else navigate(returnTo, { replace: true })
    } catch (error) {
      setFormError(loginFailureMessage(toApiFailure(error)))
      setPassword("")
    } finally {
      setSubmitting(false)
    }
  }

  const inputClass = AUTH_INPUT_CLASS
  return (
    // 최신 시안: 모달 로그인에는 부제가 없다. 주소(/login)로 열면 전처럼 "로그인하지 않아도…" 안내를 둔다.
    <AuthCard
      title="로그인"
      description={
        inOverlay
          ? undefined
          : "로그인하지 않아도 체크리스트·절차 안내·AI 질문을 이용할 수 있습니다."
      }
    >
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
            className={inputClass}
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
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={Boolean(fieldErrors.password)}
            aria-describedby={fieldErrors.password ? passwordErrorId : undefined}
            className={inputClass}
          />
          {fieldErrors.password && (
            <p id={passwordErrorId} className="text-sm text-danger-foreground">
              {fieldErrors.password}
            </p>
          )}
        </div>
        <Button type="submit" className="mt-2 h-11 w-full text-base" disabled={submitting}>
          {submitting ? "로그인 중…" : "로그인"}
        </Button>
      </form>
      <div className="space-y-2 text-center text-sm text-muted-foreground">
        <p>
          계정이 없나요?{" "}
          <AuthLink
            to="/signup"
            overlay="signup"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            회원가입
          </AuthLink>
        </p>
        <p>
          <AuthLink
            to="/auth/forgot"
            overlay="forgot"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            비밀번호를 잊으셨나요?
          </AuthLink>
        </p>
        {/* 모달에는 [닫기](X)가 있어 "로그인 없이 계속하기"는 페이지(/login)에서만 보인다. */}
        {!inOverlay && (
          <p>
            <AuthLink to="/" overlay="close">
              로그인 없이 계속하기
            </AuthLink>
          </p>
        )}
      </div>
    </AuthCard>
  )
}
