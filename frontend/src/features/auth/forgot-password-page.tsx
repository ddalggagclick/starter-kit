/*
 * 담당: [A] | 책임: 비밀번호 재설정 메일 요청 화면 /auth/forgot.
 * PRD: E5 / 태스크 5-5-3. 계약: A15 POST /api/auth/password/reset-request {email} → 202 (가입 여부 비노출).
 * 구현: 결과와 관계없이 같은 접수 문구를 보여 가입 여부를 드러내지 않는다. 네트워크 실패만 따로 안내한다.
 */
import { type FormEvent, useState } from "react"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { requestPasswordResetRequest } from "./auth-api"
import { AuthCard, AuthField, AuthLink } from "./auth-form-field"

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [result, setResult] = useState<"sent" | "error" | null>(null)
  const [sending, setSending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim()) return
    setSending(true)
    try {
      await requestPasswordResetRequest(email.trim())
      setResult("sent")
    } catch {
      setResult("error")
    } finally {
      setSending(false)
    }
  }

  return (
    <AuthCard title="비밀번호 재설정" description="가입한 이메일로 재설정 링크를 보내 드립니다.">
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        <AuthField
          label="이메일"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
        />
        <Button type="submit" className="w-full" disabled={sending || !email.trim()}>
          재설정 메일 받기
        </Button>
      </form>
      {result === "sent" && (
        <Notice tone="info">
          가입된 이메일이면 재설정 링크를 보냈습니다. 링크는 30분 동안 한 번만 쓸 수 있습니다.
        </Notice>
      )}
      {result === "error" && (
        <Notice tone="danger">요청하지 못했습니다. 잠시 후 다시 시도해 주세요.</Notice>
      )}
      <AuthLink to="/login" overlay="login">
        로그인 화면으로
      </AuthLink>
    </AuthCard>
  )
}
