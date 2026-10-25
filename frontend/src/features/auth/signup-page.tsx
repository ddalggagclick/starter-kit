/*
 * 담당: [A] | 책임: 회원가입 화면 /signup과 가입 직후 인증 메일 안내.
 * PRD: E5 / 태스크 5-1-1, 5-5-5, 5-6-1. 계약: A11 POST /api/auth/signup {email, password} → 201,
 *   409 이미 가입, 422 형식 (x-confirmed: true, 경로 제안). 이메일 인증 전에는 로그인할 수 없다.
 * 구현: 비밀번호를 서버와 같은 규칙으로 미리 검사한다. 가입하면 인증 메일 확인 안내와 재전송을 보인다.
 * 제한사항: 비밀번호를 저장·기록하지 않는다. 가입 전에도 모든 기본 기능을 쓸 수 있다는 안내를 유지한다.
 */
import { type FormEvent, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { toApiFailure } from "@/shared/api/api-error"
import { newPasswordError, PASSWORD_RULE_TEXT } from "@/shared/contracts/password-policy"
import { signupRequest } from "./auth-api"
import { AuthCard, AuthField } from "./auth-form-field"
import { ResendVerificationForm } from "./resend-verification-form"

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function SignupPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [signedUpEmail, setSignedUpEmail] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = email.trim()
    const nextEmailError = EMAIL_PATTERN.test(trimmed) ? null : "이메일 형식을 확인해 주세요."
    const nextPasswordError = newPasswordError(password, confirm)
    setEmailError(nextEmailError)
    setPasswordError(nextPasswordError)
    setFormError(null)
    if (nextEmailError || nextPasswordError) return
    setSubmitting(true)
    try {
      await signupRequest(trimmed, password)
      setSignedUpEmail(trimmed)
    } catch (error) {
      const { status } = toApiFailure(error)
      if (status === 409)
        setEmailError("이미 가입된 이메일입니다. 로그인하거나 비밀번호를 재설정해 주세요.")
      else if (status === 422)
        setFormError(`이메일 형식과 비밀번호 규칙(${PASSWORD_RULE_TEXT})을 확인해 주세요.`)
      else setFormError("가입하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    } finally {
      setSubmitting(false)
      setPassword("")
      setConfirm("")
    }
  }

  if (signedUpEmail) {
    return (
      <AuthCard title="인증 메일을 확인해 주세요">
        <Notice tone="success">
          가입 신청을 받았습니다. {signedUpEmail}로 보낸 메일의 링크를 눌러 인증을 마치면 로그인할
          수 있습니다.
        </Notice>
        <ResendVerificationForm initialEmail={signedUpEmail} />
        <Link to="/login" className="text-sm underline underline-offset-4">
          로그인 화면으로
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="회원가입"
      description="가입하지 않아도 체크리스트·절차 안내·AI 질문을 이용할 수 있습니다."
    >
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        {formError && <Notice tone="danger">{formError}</Notice>}
        <AuthField
          label="이메일"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          error={emailError}
        />
        <AuthField
          label="비밀번호"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          error={passwordError}
          hint={PASSWORD_RULE_TEXT}
        />
        <AuthField
          label="비밀번호 확인"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={setConfirm}
        />
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "가입 중…" : "가입하기"}
        </Button>
      </form>
      <Link to="/login" className="text-sm underline underline-offset-4">
        이미 계정이 있으면 로그인
      </Link>
    </AuthCard>
  )
}
