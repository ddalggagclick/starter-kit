/*
 * 담당: [A] | 책임: 비밀번호 재설정 링크 화면 /auth/reset#token=… (팀원 요청).
 * PRD: E5 / 태스크 5-5-3, 5-5-5. 계약: A15 POST /api/auth/password/reset {resetToken, newPassword}
 *   (x-confirmed: true, 경로 제안. 링크 30분·1회, 변경 시 모든 기기 로그아웃).
 * 구현: #token을 읽고 주소에서 바로 지운다. 새 비밀번호를 서버와 같은 규칙으로 검사한 뒤 보낸다.
 *   성공하면 이 탭도 로그아웃하고 로그인 안내를 보인다. 만료·이미 사용은 구분 없이 같은 안내와 재요청 경로를 보인다.
 * 제한사항: 토큰·비밀번호를 로그·저장소에 남기지 않는다. 실패를 성공으로 표시하지 않는다.
 */
import { type FormEvent, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { toApiFailure } from "@/shared/api/api-error"
import { logoutRequest, resetPasswordRequest } from "./auth-api"
import { AuthCard, AuthField } from "./auth-form-field"
import { useAuthStore } from "./auth-store"
import { useLinkToken } from "./link-token"
import { newPasswordError, PASSWORD_RULE_TEXT } from "./password-policy"

export function ResetPasswordPage() {
  const token = useLinkToken()
  const signOut = useAuthStore((s) => s.signOut)
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<"form" | "done" | "invalid">(token ? "form" : "invalid")
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!token) return
    const problem = newPasswordError(password, confirm)
    setError(problem)
    if (problem) return
    setSubmitting(true)
    try {
      await resetPasswordRequest(token, password)
      // 서버는 모든 기기를 로그아웃시킨다. 이 탭의 로그인 상태도 맞춰 해제한다.
      if (useAuthStore.getState().accountId) {
        void logoutRequest()
        signOut()
      }
      setState("done")
    } catch (failure) {
      const { status } = toApiFailure(failure)
      if (status === 422) setError(PASSWORD_RULE_TEXT)
      else if (status === 400) setState("invalid")
      else setError("변경하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    } finally {
      setSubmitting(false)
      setPassword("")
      setConfirm("")
    }
  }

  if (state === "done") {
    return (
      <AuthCard title="비밀번호 재설정">
        <Notice tone="success">
          비밀번호를 바꿨습니다. 모든 기기에서 로그아웃되었으니 새 비밀번호로 로그인해 주세요.
        </Notice>
        <Button asChild className="w-full">
          <Link to="/login">로그인하기</Link>
        </Button>
      </AuthCard>
    )
  }

  if (state === "invalid") {
    return (
      <AuthCard title="비밀번호 재설정">
        <Notice tone="danger">
          링크가 만료되었거나 이미 사용되었습니다. 재설정 메일을 다시 요청해 주세요.
        </Notice>
        <Button asChild variant="outline" className="w-full">
          <Link to="/auth/forgot">재설정 메일 다시 받기</Link>
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="비밀번호 재설정" description="새 비밀번호를 입력해 주세요.">
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        {error && <Notice tone="danger">{error}</Notice>}
        <AuthField
          label="새 비밀번호"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          hint={PASSWORD_RULE_TEXT}
        />
        <AuthField
          label="새 비밀번호 확인"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={setConfirm}
        />
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "변경 중…" : "비밀번호 변경"}
        </Button>
      </form>
    </AuthCard>
  )
}
